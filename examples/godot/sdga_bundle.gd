## Runtime consumer for the JSON written by `sdga adapt --engine godot`.
##
## The generator never imports Godot and never writes `.tres`/`.tscn` files. This script is the
## other half: it reads `sprite_frames.json`, `ninepatch.json`, `audio_buses.json` and
## `godot_import.json`, and turns them into engine objects. It is intentionally small enough to
## copy into a real project.
##
## Paths in the bundle are relative to the pack, not to the bundle directory. Resolve them
## against the pack root (the adapter's parent is `adapters/<pack_id>/`, the pack lives under
## `<project>/packs/<pack_id>/`). The sample self-check does not load textures, because the JSON
## is the contract; a real importer passes an atlas texture to `make_sprite_frames`.
extends RefCounted

const DOCUMENTS: Array[String] = [
	"audio_buses.json",
	"godot_import.json",
	"ninepatch.json",
	"sprite_frames.json",
]


static func read_json(path: String, errors: Array) -> Dictionary:
	if not FileAccess.file_exists(path):
		errors.append("missing %s" % path)
		return {}
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		errors.append("cannot open %s" % path)
		return {}
	var parsed = JSON.parse_string(file.get_as_text())
	if typeof(parsed) != TYPE_DICTIONARY:
		errors.append("invalid JSON object in %s" % path)
		return {}
	return parsed


static func load_bundle(directory: String) -> Dictionary:
	var errors: Array = []
	var documents := {}
	for name in DOCUMENTS:
		var document := read_json(directory.path_join(name), errors)
		if document.is_empty():
			continue
		if document.get("schema") != 1:
			errors.append("%s has schema %s, expected 1" % [name, document.get("schema")])
		if document.get("engine") != "godot":
			errors.append("%s is not a Godot document" % name)
		documents[name] = document
	return {"ok": errors.is_empty(), "errors": errors, "documents": documents}


## Build a SpriteFrames resource from one sprite's descriptor.
##
## `texture` is the sheet texture in a real project; `atlas_region` would be used to add one
## AtlasTexture per frame. The sample passes a placeholder because it only checks the clip
## structure. Named clips replace Godot's built-in `default` animation.
static func make_sprite_frames(
	document: Dictionary, sprite_id: String, texture: Texture2D
) -> SpriteFrames:
	var frames := SpriteFrames.new()
	var sprites: Dictionary = document.get("sprites", {})
	if not sprites.has(sprite_id):
		return frames
	var animations: Dictionary = sprites[sprite_id].get("animations", {})
	if not animations.has("default"):
		frames.remove_animation("default")
	for name in animations:
		var clip: Dictionary = animations[name]
		if not frames.has_animation(name):
			frames.add_animation(name)
		frames.set_animation_speed(name, float(clip.get("speed", 8.0)))
		frames.set_animation_loop(name, bool(clip.get("loop", true)))
		for _frame in clip.get("frames", []):
			frames.add_frame(name, texture)
	return frames


## Apply a ninepatch asset's margins to a NinePatchRect. Returns false if the asset is absent.
static func apply_ninepatch(rect: NinePatchRect, document: Dictionary, asset_id: String) -> bool:
	var assets: Dictionary = document.get("assets", {})
	if not assets.has(asset_id):
		return false
	var margins: Dictionary = assets[asset_id].get("margins", {})
	for edge in ["left", "top", "right", "bottom"]:
		if not margins.has(edge):
			return false
	rect.patch_margin_left = int(margins["left"])
	rect.patch_margin_top = int(margins["top"])
	rect.patch_margin_right = int(margins["right"])
	rect.patch_margin_bottom = int(margins["bottom"])
	return true
