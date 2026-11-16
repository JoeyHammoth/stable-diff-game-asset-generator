## Headless self-check for the adapter output.
##
##   godot --headless --path examples/godot --script res://import_bundle.gd -- \
##       /absolute/path/to/adapters/<pack_id>/godot /absolute/path/to/packs/<pack_id>
##
## It loads the generated sprite sheet and UI texture from the pack, builds real `AtlasTexture`
## frame regions on a real `SpriteFrames`, applies the UI texture to a `NinePatchRect`, and
## checks the bus map. A missing bundle or asset exits non-zero with the reason.
extends SceneTree

const Bundle = preload("res://sdga_bundle.gd")

var failures: Array[String] = []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	if args.size() < 2:
		push_error("usage: -- <bundle-dir> <pack-dir>")
		quit(2)
		return
	var directory := args[0]
	var pack_root := args[1]
	var loaded := Bundle.load_bundle(directory)
	for error in loaded["errors"]:
		failures.append(error)
	if failures.is_empty():
		_check(loaded["documents"], pack_root)
	if failures.is_empty():
		print(
			"godot adapter sample: ok "
			+ "(walk 8 atlas frames @ 10 fps, sheet 256x32, UI 64x16, margins 31/7/31/7, "
			+ "buses Music,SFX)"
		)
		quit(0)
		return
	for failure in failures:
		push_error(failure)
	quit(1)


func _check(documents: Dictionary, pack_root: String) -> void:
	_check_sprite_frames(documents["sprite_frames.json"], pack_root)
	_check_ninepatch(documents["ninepatch.json"], pack_root)
	_check_audio(documents["audio_buses.json"])
	_check_imports(documents["godot_import.json"])


func _load_texture(pack_root: String, relative: String) -> Texture2D:
	var path := pack_root.path_join(relative)
	if not FileAccess.file_exists(path):
		failures.append("missing generated texture %s" % path)
		return null
	var image := Image.load_from_file(path)
	if image == null:
		failures.append("cannot decode generated texture %s" % path)
		return null
	return ImageTexture.create_from_image(image)


func _check_sprite_frames(document: Dictionary, pack_root: String) -> void:
	var sprites: Dictionary = document.get("sprites", {})
	if not sprites.has("char/ranger_walk"):
		failures.append("sprite_frames.json has no char/ranger_walk")
		return
	var sprite: Dictionary = sprites["char/ranger_walk"]
	var animations: Dictionary = sprite.get("animations", {})
	var walk: Dictionary = animations.get("walk", {})
	var frames: Array = walk.get("frames", [])
	if frames.size() != 8:
		failures.append("walk has %d frames, expected 8" % frames.size())
		return
	for index in range(8):
		if int(frames[index]) != index:
			failures.append("walk frame %d is %s" % [index, frames[index]])
			return
	if not is_equal_approx(float(walk.get("speed", 0.0)), 10.0):
		failures.append("walk speed is %s, expected 10" % walk.get("speed"))
	if walk.get("loop") != true:
		failures.append("walk does not loop")

	var sheet := _load_texture(pack_root, str(sprite["path"]))
	if sheet == null:
		return
	var frame_size: Array = sprite["frame_size"]
	var expected := Vector2(
		float(frame_size[0]) * float(sprite["cols"]),
		float(frame_size[1]) * float(sprite["rows"])
	)
	if sheet.get_size() != expected:
		failures.append("sheet is %s, expected %s" % [sheet.get_size(), expected])

	var built := Bundle.make_sprite_frames(document, "char/ranger_walk", sheet)
	if not built.has_animation("walk"):
		failures.append("SpriteFrames has no walk animation")
		return
	if built.get_frame_count("walk") != 8:
		failures.append("SpriteFrames walk has %d frames" % built.get_frame_count("walk"))
	if not is_equal_approx(built.get_animation_speed("walk"), 10.0):
		failures.append("SpriteFrames walk speed is %s" % built.get_animation_speed("walk"))
	if not built.get_animation_loop("walk"):
		failures.append("SpriteFrames walk is not looping")
	if built.has_animation("default"):
		failures.append("SpriteFrames kept a default clip alongside the named clip")

	var first := built.get_frame_texture("walk", 0) as AtlasTexture
	if first == null:
		failures.append("SpriteFrames walk frame 0 is not an AtlasTexture")
	elif first.atlas != sheet:
		failures.append("SpriteFrames walk frame 0 uses a different texture")
	elif first.region != Rect2(0, 0, float(frame_size[0]), float(frame_size[1])):
		failures.append("SpriteFrames walk frame 0 region is %s" % first.region)


func _check_ninepatch(document: Dictionary, pack_root: String) -> void:
	var rect := NinePatchRect.new()
	if not Bundle.apply_ninepatch(rect, document, "ui/button_normal"):
		failures.append("ninepatch.json has no ui/button_normal margins")
		rect.free()
		return
	var ui: Dictionary = document.get("assets", {}).get("ui/button_normal", {})
	var texture := _load_texture(pack_root, str(ui.get("path", "")))
	if texture == null:
		rect.free()
		return
	rect.texture = texture
	if rect.texture == null:
		failures.append("NinePatchRect did not accept the generated UI texture")
	if texture.get_size() != Vector2(64, 16):
		failures.append("UI texture is %s, expected 64x16" % texture.get_size())
	if rect.patch_margin_left != 31 or rect.patch_margin_top != 7:
		failures.append(
			"NinePatchRect margins are %d/%d/%d/%d"
			% [
				rect.patch_margin_left,
				rect.patch_margin_top,
				rect.patch_margin_right,
				rect.patch_margin_bottom,
			]
		)
	if rect.patch_margin_right != 31 or rect.patch_margin_bottom != 7:
		failures.append("NinePatchRect right/bottom margins are wrong")
	rect.free()


func _check_audio(document: Dictionary) -> void:
	var names: Array = []
	for bus in document.get("buses", []):
		names.append(bus.get("name"))
	if not names.has("Music") or not names.has("SFX"):
		failures.append("audio buses are %s, expected Music and SFX" % [names])
	var assets: Dictionary = document.get("assets", {})
	if assets.get("music/title", {}).get("bus") != "Music":
		failures.append("music/title is not on the Music bus")
	if assets.get("sfx/pickup", {}).get("one_shot") != true:
		failures.append("sfx/pickup is not a one-shot")


func _check_imports(document: Dictionary) -> void:
	var files: Dictionary = document.get("files", {})
	var terrain: Dictionary = files.get("assets/terrain/moss_stone.png", {})
	if terrain.get("filter") != false or terrain.get("mipmaps") != false:
		failures.append("terrain texture does not disable filter/mipmaps")
	var music: Dictionary = files.get("assets/music/title.wav", {})
	if music.get("loop_mode") != 1:
		failures.append("music WAV is not set to forward loop")
	if music.get("loop_end_frame", 0) <= 0:
		failures.append("music WAV has no loop end frame")
