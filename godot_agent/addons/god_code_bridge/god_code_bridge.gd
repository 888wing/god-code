## GodCodeBridge — TCP JSON-RPC server for god-code AI agent.
##
## Add as an autoload in project.godot to expose a live runtime bridge
## on TCP port 9394.  god-code's LiveRuntimeClient connects here to
## inspect the scene tree, read node properties, capture the viewport,
## and inject input actions — all without touching the Godot debugger.
##
## Protocol: newline-delimited JSON-RPC 2.0 over TCP.
extends Node

const PORT := 9394
const MAX_PENDING := 4

var _server: TCPServer = null
var _peers: Array[StreamPeerTCP] = []
var _signal_log: Array[Dictionary] = []
const _MAX_SIGNAL_LOG := 200


func _ready() -> void:
	_server = TCPServer.new()
	var err := _server.listen(PORT)
	if err != OK:
		push_warning("GodCodeBridge: failed to listen on port %d (err %d)" % [PORT, err])
		return
	print("GodCodeBridge: listening on TCP port %d" % PORT)


func _process(_delta: float) -> void:
	if _server == null:
		return
	# Accept new connections.
	while _server.is_connection_available():
		var peer := _server.take_connection()
		if peer:
			_peers.append(peer)
			print("GodCodeBridge: client connected (%d active)" % _peers.size())
	# Process each peer.
	var stale: Array[int] = []
	for i in range(_peers.size()):
		var peer := _peers[i]
		peer.poll()
		var status := peer.get_status()
		if status != StreamPeerTCP.STATUS_CONNECTED:
			stale.append(i)
			continue
		if peer.get_available_bytes() > 0:
			var raw := peer.get_utf8_string(peer.get_available_bytes())
			if raw.length() > 0:
				_handle_messages(peer, raw)
	# Remove disconnected peers (reverse order).
	for i in range(stale.size() - 1, -1, -1):
		_peers.remove_at(stale[i])


func _handle_messages(peer: StreamPeerTCP, raw: String) -> void:
	for line in raw.split("\n", false):
		var parsed = JSON.parse_string(line)
		if parsed == null or not parsed is Dictionary:
			_send_error(peer, null, -32700, "Parse error")
			continue
		var req: Dictionary = parsed
		var id = req.get("id")
		var method: String = req.get("method", "")
		var params = req.get("params", {})
		if params == null:
			params = {}
		var result = _dispatch(method, params)
		if result is Dictionary and result.has("__error__"):
			_send_error(peer, id, result["__code__"], result["__error__"])
		else:
			_send_result(peer, id, result)


func _dispatch(method: String, params) -> Variant:
	match method:
		"ping":
			return {"pong": true}
		"get_scene_tree":
			return _rpc_get_scene_tree()
		"get_node_properties":
			var path: String = params.get("path", "") if params is Dictionary else ""
			return _rpc_get_node_properties(path)
		"capture_viewport":
			return _rpc_capture_viewport()
		"inject_action":
			var action: String = params.get("action", "") if params is Dictionary else ""
			var pressed: bool = params.get("pressed", true) if params is Dictionary else true
			return _rpc_inject_action(action, pressed)
		"get_signals":
			return _signal_log.duplicate()
		_:
			return {"__error__": "Method not found: %s" % method, "__code__": -32601}


# ── RPC handlers ──────────────────────────────────────────────────

func _rpc_get_scene_tree() -> Array:
	var result: Array = []
	var root := get_tree().root
	_walk_tree(root, result)
	return result


func _walk_tree(node: Node, out: Array) -> void:
	out.append({
		"path": str(node.get_path()),
		"type": node.get_class(),
		"visible": node.is_inside_tree(),
		"children_count": node.get_child_count(),
	})
	for child in node.get_children():
		_walk_tree(child, out)


func _rpc_get_node_properties(path: String) -> Variant:
	if path.is_empty():
		return {"__error__": "Missing 'path' parameter", "__code__": -32602}
	var node := get_node_or_null(NodePath(path))
	if node == null:
		return {"__error__": "Node not found: %s" % path, "__code__": -32602}
	var props := {}
	props["class"] = node.get_class()
	props["name"] = node.name
	if node is Node2D:
		props["position"] = {"x": node.position.x, "y": node.position.y}
		props["rotation"] = node.rotation
		props["scale"] = {"x": node.scale.x, "y": node.scale.y}
		props["visible"] = node.visible
	if node is Control:
		props["position"] = {"x": node.position.x, "y": node.position.y}
		props["size"] = {"x": node.size.x, "y": node.size.y}
		props["visible"] = node.visible
	if node is CanvasItem:
		props["modulate"] = {
			"r": node.modulate.r,
			"g": node.modulate.g,
			"b": node.modulate.b,
			"a": node.modulate.a,
		}
	if "text" in node:
		props["text"] = str(node.text)
	return props


func _rpc_capture_viewport() -> Dictionary:
	var img := get_viewport().get_texture().get_image()
	if img == null:
		return {"__error__": "Viewport capture failed", "__code__": -32603}
	var png := img.save_png_to_buffer()
	return {"image_b64": Marshalls.raw_to_base64(png)}


func _rpc_inject_action(action: String, pressed: bool) -> Dictionary:
	if action.is_empty():
		return {"__error__": "Missing 'action' parameter", "__code__": -32602}
	var ev := InputEventAction.new()
	ev.action = action
	ev.pressed = pressed
	Input.parse_input_event(ev)
	return {"ok": true}


# ── Signal logging ────────────────────────────────────────────────

## Call this from gameplay code to log signals for god-code inspection.
## Example: GodCodeBridge.log_signal("health_changed", self)
func log_signal(signal_name: String, source: Node) -> void:
	_signal_log.append({
		"signal_name": signal_name,
		"source": str(source.get_path()) if source else "",
		"tick": Engine.get_process_frames(),
	})
	if _signal_log.size() > _MAX_SIGNAL_LOG:
		_signal_log.pop_front()


# ── Transport helpers ─────────────────────────────────────────────

func _send_result(peer: StreamPeerTCP, id, result) -> void:
	var resp := JSON.stringify({"jsonrpc": "2.0", "id": id, "result": result})
	peer.put_data((resp + "\n").to_utf8_buffer())


func _send_error(peer: StreamPeerTCP, id, code: int, message: String) -> void:
	var resp := JSON.stringify({
		"jsonrpc": "2.0",
		"id": id,
		"error": {"code": code, "message": message},
	})
	peer.put_data((resp + "\n").to_utf8_buffer())
