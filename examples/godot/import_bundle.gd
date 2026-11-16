## Headless self-check for the adapter output.
##
##   godot --headless --path examples/godot --script res://import_bundle.gd -- \
##       /absolute/path/to/adapters/<pack_id>/godot
##
## It builds a real `SpriteFrames`, a real `NinePatchRect`, and checks the bus map, so the
## sample fails if the adapter's contract drifts. A missing bundle path exits 1 with the reason.
extends SceneTree

const Bundle = preload("res://sdga_bundle.gd")

var failures: Array[String] = []


func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var directory := args[0] if not args.is_empty() else "res://bundle"
	var loaded := Bundle.load_bundle(directory)
	for error in loaded["errors"]:
		failures.append(error)
	if failures.is_empty():
		_check(loaded["documents"])
	if failures.is_empty():
		print(
			"godot adapter sample: ok "
			+ "(walk 8 frames @ 10 fps, margins 31/7/31/7, buses Music,SFX)"
		)
		quit(0)
		return
	for failure in failures:
		push_error(failure)
	quit(1)


func _check(documents: Dictionary) -> void:
	_check_sprite_frames(documents["sprite_frames.json"])
	_check_ninepatch(documents["ninepatch.json"])
	_check_audio(documents["audio_buses.json"])
	_check_imports(documents["godot_import.json"])


func _check_sprite_frames(document: Dictionary) -> void:
	var sprites: Dictionary = document.get("sprites", {})
	if not sprites.has("char/ranger_walk"):
		failures.append("sprite_frames.json has no char/ranger_walk")
		return
	var animations: Dictionary = sprites["char/ranger_walk"].get("animations", {})
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

	var image := Image.create(1, 1, false, Image.FORMAT_RGBA8)
	image.fill(Color.MAGENTA)
	var texture := ImageTexture.create_from_image(image)
	var built := Bundle.make_sprite_frames(document, "char/ranger_walk", texture)
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


func _check_ninepatch(document: Dictionary) -> void:
	var rect := NinePatchRect.new()
	if not Bundle.apply_ninepatch(rect, document, "ui/button_normal"):
		failures.append("ninepatch.json has no ui/button_normal margins")
		rect.free()
		return
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
