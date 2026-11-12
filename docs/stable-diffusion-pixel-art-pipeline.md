# Stable Diffusion Pixel Art Asset Pipeline for Godot Game Development
## Windows 11 Installation & Setup Guide

> **Goal:** A fully local, automated AI-driven asset factory that generates stylistically consistent pixel art — concept art, character sprites, animations, UI/HUD, terrain, and shader-ready assets — plus a cohesive, leitmotif-driven orchestral soundtrack — all integrated with Godot 4 and Claude Code.

---

## Table of Contents

1. [System Requirements](#1-system-requirements)
2. [Core Software Installation](#2-core-software-installation)
3. [ComfyUI Setup & Essential Nodes](#3-comfyui-setup--essential-nodes)
4. [Style Consistency Foundation](#4-style-consistency-foundation)
5. [Asset Pipeline by Type](#5-asset-pipeline-by-type)
   - 5.1 [Concept Art Generation](#51-concept-art-generation)
   - 5.2 [Character Sprite Sheets & Animation](#52-character-sprite-sheets--animation)
   - 5.3 [Environmental & Terrain Tiles](#53-environmental--terrain-tiles)
   - 5.4 [UI, HUD, Menus & Buttons](#54-ui-hud-menus--buttons)
   - 5.5 [Normal Maps for 2D Lighting](#55-normal-maps-for-2d-lighting)
6. [Noise Removal & Reference Cleaning](#6-noise-removal--reference-cleaning)
7. [LoRA Training for Style Lock-In](#7-lora-training-for-style-lock-in)
8. [Audio Asset Pipeline (SFX & Voice)](#8-audio-asset-pipeline)
9. [Godot 4 Integration](#9-godot-4-integration)
10. [Claude Code Integration](#10-claude-code-integration)
11. [Project Folder Structure](#11-project-folder-structure)
12. [Style Config Reference](#12-style-config-reference)
13. [Music Generation Pipeline](#13-music-generation-pipeline)
    - 13.1 [Music Stack Overview](#131-music-stack-overview)
    - 13.2 [Installation: Music Tools](#132-installation-music-tools)
    - 13.3 [Layer 1 — Symbolic Composition (The Brain)](#133-layer-1--symbolic-composition-the-brain)
    - 13.4 [Layer 2 — Audio Synthesis (The Orchestra)](#134-layer-2--audio-synthesis-the-orchestra)
    - 13.5 [Layer 3 — Post-Processing & Looping (The Studio)](#135-layer-3--post-processing--looping-the-studio)
    - 13.6 [Layer 4 — Leitmotif Consistency Enforcement](#136-layer-4--leitmotif-consistency-enforcement)
    - 13.7 [Biome-by-Biome Generation Guide](#137-biome-by-biome-generation-guide)
    - 13.8 [Seamless Loop Engineering](#138-seamless-loop-engineering)
    - 13.9 [Godot 4 Adaptive Music Integration](#139-godot-4-adaptive-music-integration)
    - 13.10 [Music Generation Checklist](#1310-music-generation-checklist)
14. [ComfyUI Workflow Scripting (No GUI)](#14-comfyui-workflow-scripting-no-gui)
    - 14.1 [How the ComfyUI API Works](#141-how-the-comfyui-api-works)
    - 14.2 [Reading and Exporting Workflows as JSON](#142-reading-and-exporting-workflows-as-json)
    - 14.3 [The WorkflowBuilder Class](#143-the-workflowbuilder-class)
    - 14.4 [Pre-Built Workflow Scripts by Asset Type](#144-pre-built-workflow-scripts-by-asset-type)
    - 14.5 [Uploading Reference Images Programmatically](#145-uploading-reference-images-programmatically)
15. [Batch Automation System](#15-batch-automation-system)
    - 15.1 [Architecture Overview](#151-architecture-overview)
    - 15.2 [Prompt Manifest System](#152-prompt-manifest-system)
    - 15.3 [Batch Generation from Prompt Arrays](#153-batch-generation-from-prompt-arrays)
    - 15.4 [Folder Ingestion Pipeline](#154-folder-ingestion-pipeline)
    - 15.5 [The Master Automation Orchestrator](#155-the-master-automation-orchestrator)
    - 15.6 [Post-Generation Hooks](#156-post-generation-hooks)
16. [Godot 4 Installation & Project Setup](#16-godot-4-installation--project-setup)
    - 16.1 [Installing Godot 4](#161-installing-godot-4)
    - 16.2 [Creating a New Project](#162-creating-a-new-project)
    - 16.3 [Pixel Art Rendering Configuration](#163-pixel-art-rendering-configuration)
    - 16.4 [Project Folder Structure in Godot](#164-project-folder-structure-in-godot)
    - 16.5 [Import Settings for AI-Generated Assets](#165-import-settings-for-ai-generated-assets)
    - 16.6 [Audio Bus Configuration](#166-audio-bus-configuration)
    - 16.7 [Autoload Setup](#167-autoload-setup)
    - 16.8 [Recommended Plugins](#168-recommended-plugins)
    - 16.9 [Live Asset Hot-Reload Integration](#169-live-asset-hot-reload-integration)
    - 16.10 [End-to-End Integration Flow](#1610-end-to-end-integration-flow)
14. [ComfyUI Workflow Scripting (No GUI)](#14-comfyui-workflow-scripting-no-gui)
    - 14.1 [How the ComfyUI API Works](#141-how-the-comfyui-api-works)
    - 14.2 [Reading and Exporting Workflows as JSON](#142-reading-and-exporting-workflows-as-json)
    - 14.3 [The WorkflowBuilder Class](#143-the-workflowbuilder-class)
    - 14.4 [Pre-Built Workflow Scripts by Asset Type](#144-pre-built-workflow-scripts-by-asset-type)
    - 14.5 [Uploading Reference Images Programmatically](#145-uploading-reference-images-programmatically)
15. [Batch Automation System](#15-batch-automation-system)
    - 15.1 [Architecture Overview](#151-architecture-overview)
    - 15.2 [Prompt Manifest System](#152-prompt-manifest-system)
    - 15.3 [Batch Generation from Prompt Arrays](#153-batch-generation-from-prompt-arrays)
    - 15.4 [Folder Ingestion Pipeline](#154-folder-ingestion-pipeline)
    - 15.5 [The Master Automation Orchestrator](#155-the-master-automation-orchestrator)
    - 15.6 [Post-Generation Hooks](#156-post-generation-hooks)
16. [Godot 4 Installation & Project Setup](#16-godot-4-installation--project-setup)
    - 16.1 [Installing Godot 4](#161-installing-godot-4)
    - 16.2 [Creating a New Project](#162-creating-a-new-project)
    - 16.3 [Pixel Art Rendering Configuration](#163-pixel-art-rendering-configuration)
    - 16.4 [Project Folder Structure in Godot](#164-project-folder-structure-in-godot)
    - 16.5 [Import Settings for AI-Generated Assets](#165-import-settings-for-ai-generated-assets)
    - 16.6 [Audio Bus Configuration](#166-audio-bus-configuration)
    - 16.7 [Autoload Setup](#167-autoload-setup)
    - 16.8 [Recommended Plugins](#168-recommended-plugins)
    - 16.9 [Live Asset Hot-Reload Integration](#169-live-asset-hot-reload-integration)
    - 16.10 [End-to-End Integration Flow](#1610-end-to-end-integration-flow)

---

## 1. System Requirements

### Minimum Specifications

| Component | Minimum | Recommended |
|---|---|---|
| **OS** | Windows 11 (64-bit) | Windows 11 23H2+ |
| **CPU** | Intel i5-8th Gen / Ryzen 5 3600 | Intel i7-12th Gen / Ryzen 7 5800X |
| **RAM** | 16 GB DDR4 | 32 GB DDR4 |
| **GPU** | NVIDIA RTX 3060 (12 GB VRAM) | NVIDIA RTX 4070 Ti (16 GB VRAM) |
| **Storage** | 60 GB free (SSD) | 150 GB+ free (NVMe SSD) |
| **Python** | 3.10.x | 3.10.11 |

> **Important:** AMD GPUs require additional ROCm configuration and are not covered in this guide. NVIDIA GPUs with CUDA support are strongly recommended.

### Pre-Installation Checklist

- [ ] NVIDIA drivers updated (version 535.x or newer)
- [ ] CUDA Toolkit 11.8 or 12.1 installed
- [ ] Git for Windows installed
- [ ] Python 3.10.11 installed (add to PATH during installation)
- [ ] Microsoft Visual C++ Redistributable installed

---

## 2. Core Software Installation

### 2.1 Install Git for Windows

Download from [https://git-scm.com/download/win](https://git-scm.com/download/win) and install with default settings.

### 2.2 Install Python 3.10.11

1. Download Python 3.10.11 from [https://www.python.org/downloads/release/python-31011/](https://www.python.org/downloads/release/python-31011/)
2. **Critical:** Check "Add Python to PATH" during installation
3. Verify installation:

```bash
python --version
# Expected: Python 3.10.11
```

### 2.3 Install CUDA Toolkit

Download CUDA 11.8 from NVIDIA's developer portal. During installation, select **Custom Install** and ensure the following are checked:
- CUDA Development
- CUDA Runtime
- CUDA Visual Studio Integration (optional)

Verify installation:

```bash
nvcc --version
# Expected: Cuda compilation tools, release 11.8
```

### 2.4 Install ComfyUI (Primary Generation Backend)

ComfyUI is the node-based interface that will serve as the API backend for all AI generation.

```bash
# Navigate to your preferred installation directory (e.g., D:\AI\)
cd D:\AI

# Clone the repository
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# Install PyTorch with CUDA support (CUDA 11.8)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install ComfyUI dependencies
pip install -r requirements.txt
```

**First launch test:**

```bash
python main.py --listen --enable-cors --port 8188
```

Open your browser to `http://127.0.0.1:8188` — you should see the ComfyUI node interface.

### 2.5 Install ComfyUI Manager

ComfyUI Manager allows you to install custom nodes from within the browser interface.

```bash
cd D:\AI\ComfyUI\custom_nodes
git clone https://github.com/ltdrdata/ComfyUI-Manager.git
```

Restart ComfyUI. You will now see a **Manager** button in the interface.

---

## 3. ComfyUI Setup & Essential Nodes

### 3.1 Download Base Models

Place all downloaded model files in `D:\AI\ComfyUI\models\checkpoints\`

| Model | Purpose | Where to Download |
|---|---|---|
| **SDXL Base 1.0** | High-res concept art, title screens | Hugging Face (stabilityai/stable-diffusion-xl-base-1.0) |
| **Stable Diffusion 1.5** | Character sprites, UI, terrain tiles | Hugging Face (runwayml/stable-diffusion-v1-5) |
| **AnimateDiff v3** | Frame-consistent character animation | Hugging Face (guoyww/animatediff) |

Place AnimateDiff motion modules in: `D:\AI\ComfyUI\models\animatediff_models\`

### 3.2 Download Pixel Art LoRAs

Place all `.safetensors` LoRA files in `D:\AI\ComfyUI\models\loras\`

Recommended LoRAs from [Civitai.com](https://civitai.com):
- **Pixel Art v1** — General pixel art enforcer for SD 1.5
- **Retro Pixels** — Strict retro 8-bit/16-bit style
- **PixelArtXL** — SDXL-compatible pixel LoRA for concept art

### 3.3 Install Essential Custom Nodes

Via ComfyUI Manager (click **Manager → Install Custom Nodes**), install the following:

| Node Package | Purpose |
|---|---|
| `ComfyUI-ControlNet-Aux` | ControlNet preprocessors (Canny, Depth, OpenPose) |
| `ComfyUI_IPAdapter_plus` | IP-Adapter for image-based style anchoring |
| `ComfyUI-AnimateDiff-Evolved` | Frame-consistent animation generation |
| `ComfyUI-RIFE-VFI` | AI frame interpolation for smoother animations |
| `ComfyUI-Essentials` | Palette matching, image utilities |
| `ComfyUI-post-processing-nodes` | Color grading, pixel effects |
| `comfyui_controlnet_preprocessors` | Additional ControlNet models |
| `ComfyUI-layerdiffuse` | Transparent background (alpha) generation |

After installing, restart ComfyUI.

### 3.4 Download ControlNet Models

Place ControlNet models in `D:\AI\ComfyUI\models\controlnet\`

| Model | Use Case |
|---|---|
| `control_v11p_sd15_canny` | Edge-line structure for UI frames and environments |
| `control_v11p_sd15_openpose` | Skeleton-driven character animation |
| `control_v11f1p_sd15_depth` | Depth-map structure for monsters and objects |
| `control_v11p_sd15_seg` | Segmentation map for concept art → asset conversion |

Download from Hugging Face (lllyasviel/ControlNet-v1-1).

### 3.5 Launch ComfyUI in API Mode

Create a batch file `launch_comfyui.bat` in your ComfyUI root:

```bat
@echo off
cd D:\AI\ComfyUI
python main.py --listen 0.0.0.0 --enable-cors --port 8188 --preview-method auto
pause
```

Run this batch file every time before using the pipeline. ComfyUI must be running for Claude Code to communicate with it.

---

## 4. Style Consistency Foundation

This section is the most critical part of the entire guide. Inconsistency is the primary failure mode of AI-generated game assets. The system below applies a multi-layer lock to every single asset generated.

### 4.1 The Three Pillars of Style Enforcement

```
Layer 1: Neural Lock     → Custom LoRA trained on your curated dataset
Layer 2: Color Lock      → Master palette.png enforced via Palette Match node
Layer 3: Resolution Lock → Strict downscaling to your target pixel grid size
```

### 4.2 Define Your Master Palette

1. Go to [Lospec.com/palette-list](https://lospec.com/palette-list)
2. Choose a palette that fits your game's visual identity (e.g., "Endesga 32" for fantasy, "Pear36" for retro, "Apollo" for bright platformers)
3. Download the palette as a `.png` file
4. Save to: `D:\GameProject\style\master_palette.png`

### 4.3 Create the Global Style Config

Create `D:\GameProject\style_config.json`:

```json
{
  "project_name": "MyPixelGame",
  "pixel_grid_size": 32,
  "generation_resolution": 512,
  "master_palette_path": "D:/GameProject/style/master_palette.png",
  "style_anchor_path": "D:/GameProject/style/style_anchor.png",
  "lora_name": "my_game_style.safetensors",
  "lora_strength": 0.85,
  "base_model": "sd_v1-5.safetensors",
  "positive_anchors": [
    "ProjectMyGameStyle",
    "flat colors",
    "clean pixel art",
    "crisp outlines",
    "limited palette",
    "orthogonal view",
    "2d sprite",
    "retro game art"
  ],
  "negative_anchors": [
    "photorealistic",
    "blurry",
    "gradient",
    "smooth shading",
    "3d render",
    "watermark",
    "text",
    "sub-pixel artifacts",
    "anti-aliasing",
    "low quality",
    "deformed"
  ],
  "animatediff_fps": 12,
  "comfyui_api_url": "http://127.0.0.1:8188"
}
```

### 4.4 Palette Enforcement Workflow in ComfyUI

For every workflow you build, always insert this node chain **after** the final image output and **before** saving:

```
[VAE Decode] → [Palette Match Node] → [Pixel Art Downscale] → [Save Image]
                       ↑
               (Load master_palette.png)
```

In the **Palette Match** node (from ComfyUI-Essentials):
- Set `palette_image`: load your `master_palette.png`
- Set `dither`: `False` (hard snap, no dithering)

In the **Pixel Art Downscale** node:
- Set `scale_by`: `0.0625` (for 512→32) or `0.125` (for 512→64)
- Set `resampling`: `Nearest` (critical — never use Bilinear or Lanczos)

---

## 5. Asset Pipeline by Type

### 5.1 Concept Art Generation

Concept art is generated first at high resolution, cleaned, and then used as the IP-Adapter reference for all downstream production assets.

#### Step 1: Build the Concept Art Workflow in ComfyUI

Node chain for concept art:

```
[CLIP Text Encode (Positive)] ─┐
                                ├→ [KSampler] → [VAE Decode] → [Palette Match] → [Save PNG]
[CLIP Text Encode (Negative)] ─┘      ↑
                                  [CheckpointLoader: SDXL]
                                  [LoRA Loader: PixelArtXL]
```

#### Step 2: Prompting for Concept Art

Structure every concept art prompt with this formula:

```
[STYLE TOKEN], [CHARACTER/ENVIRONMENT DESCRIPTION], [VIEW ANGLE], [BACKGROUND], [LIGHTING]
```

**Character Concept Example:**
```
ProjectMyGameStyle, full body concept art of a forest ranger character,
brown leather armor, green hooded cloak, wooden bow, orthographic front view,
pure white background, flat cel-shaded lighting, pixel art aesthetic
```

**Environment Concept Example:**
```
ProjectMyGameStyle, concept art of an ancient stone dungeon corridor,
moss-covered walls, flickering torch sconces, isometric view,
dark fantasy lighting, muted color palette, pixel art aesthetic
```

#### Step 3: Save Concept Art Reference Structure

```
D:\GameProject\res\concepts\
    characters\
        ranger_front.png
        ranger_back.png
        ranger_side.png
    environments\
        dungeon_corridor.png
        forest_clearing.png
    ui\
        menu_frame_concept.png
```

---

### 5.2 Character Sprite Sheets & Animation

#### Static Sprite Generation Workflow

```
[CLIP Text Encode (Positive)] ─┐
[IP-Adapter: concept_ref.png] ─┼→ [KSampler] → [VAE Decode] → [Palette Match] → [Downscale] → [Save]
[ControlNet: OpenPose Skeleton]─┘      ↑
                                  [CheckpointLoader: SD 1.5]
                                  [LoRA Loader: pixel_art_v1]
```

**IP-Adapter Settings:**
- `weight`: 0.7–0.85
- `noise`: 0.1
- `start_at`: 0.0
- `end_at`: 1.0

**ControlNet (OpenPose) Settings:**
- `strength`: 0.85
- `start_percent`: 0.0
- `end_percent`: 0.8

#### OpenPose Skeleton Templates

Download pre-made OpenPose skeleton sheets for standard game animations:
- `walk_cycle_8frame.png` — 8-pose horizontal walking skeleton
- `jump_3frame.png` — Wind-up, peak, landing poses
- `idle_2frame.png` — Breathing idle loop
- `attack_4frame.png` — Attack wind-up and follow-through

Save these skeleton sheets to: `D:\GameProject\style\skeletons\`

#### Animation Generation with AnimateDiff

For frame-consistent animation, extend the static sprite workflow:

```
[CLIP Text Encode] ─┐
[IP-Adapter: ref]  ─┼→ [AnimateDiff Loader] → [KSampler (Video)] → [VAE Decode Batch]
[OpenPose Video]   ─┘         ↑                                            ↓
                       [Motion Module v3]                       [Frame Interpolation: RIFE]
                                                                            ↓
                                                                    [Sprite Sheet Compiler]
                                                                            ↓
                                                                   [Palette Match] → [Save]
```

**AnimateDiff Settings for Pixel Art:**
- `frame_count`: 24 (generate high density, trim later in Godot)
- `fps`: 8
- `motion_scale`: 0.8 (lower = less jitter)
- `context_length`: 16

**RIFE Frame Interpolation Settings:**
- Set `multiplier` to `2` to double your frame count for smoother results

#### Post-Processing: Auto-Centering Script

Save this as `D:\GameProject\tools\center_sprite_sheet.py`:

```python
import os
from PIL import Image
import numpy as np

def center_sprite_in_cell(input_path: str, output_path: str, cell_size: int = 32, cols: int = 8):
    """
    Takes a raw AI sprite sheet and centers each frame within a strict pixel grid cell.
    Prevents jitter/shake when played back in Godot.
    """
    sheet = Image.open(input_path).convert("RGBA")
    sheet_w, sheet_h = sheet.size
    rows = sheet_h // cell_size

    output = Image.new("RGBA", (cols * cell_size, rows * cell_size), (0, 0, 0, 0))

    for row in range(rows):
        for col in range(cols):
            # Extract frame
            x = col * (sheet_w // cols)
            y = row * cell_size
            frame = sheet.crop((x, y, x + (sheet_w // cols), y + cell_size))

            # Find bounding box of non-transparent pixels
            frame_np = np.array(frame)
            alpha = frame_np[:, :, 3]
            rows_nz, cols_nz = np.where(alpha > 10)

            if len(rows_nz) == 0:
                continue

            # Calculate center of mass
            cy = int((rows_nz.min() + rows_nz.max()) / 2)
            cx = int((cols_nz.min() + cols_nz.max()) / 2)

            # Crop tightly around sprite
            crop = frame.crop((
                cols_nz.min(), rows_nz.min(),
                cols_nz.max() + 1, rows_nz.max() + 1
            ))

            # Paste centered into output cell
            paste_x = col * cell_size + (cell_size - crop.width) // 2
            paste_y = row * cell_size + (cell_size - crop.height) // 2
            output.paste(crop, (paste_x, paste_y), crop)

    output.save(output_path)
    print(f"Centered sprite sheet saved to: {output_path}")


if __name__ == "__main__":
    import sys
    center_sprite_in_cell(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 32)
```

Usage:
```bash
python center_sprite_sheet.py raw_walk.png res/sprites/player_walk.png 32
```

---

### 5.3 Environmental & Terrain Tiles

#### Seamless Tiling Workflow

The key to tileable textures is the **Make Tiling** node, which wraps edges before generation.

```
[CLIP Text Encode (Positive)] ─┐
[IP-Adapter: env_concept.png] ─┼→ [KSampler] → [VAE Decode] → [Make Tiling] → [Palette Match] → [Downscale] → [Save]
[ControlNet: Canny from concept]─┘      ↑
                                  [CheckpointLoader: SD 1.5]
                                  [LoRA Loader: pixel_art_v1]
```

**Make Tiling Node Settings:**
- `tiling`: Enable both X and Y axes

**Output Resolutions:**
- Ground tiles: `32×32` px
- Large terrain blocks: `64×64` px
- Background layers: `128×128` px or `256×256` px

#### Terrain Tile Prompt Formula

```
ProjectMyGameStyle, seamless tileable [SURFACE TYPE] texture,
top-down 2d game tile, [COLOR DESCRIPTION], pixel art, flat,
no gradients, retro game aesthetic
```

**Examples:**
```
ProjectMyGameStyle, seamless tileable mossy cobblestone floor texture,
top-down 2d game tile, dark grey and green tones, pixel art, flat, no gradients
```

```
ProjectMyGameStyle, seamless tileable wooden plank floor,
side-scrolling 2d game tile, warm brown tones, pixel art, retro RPG style
```

---

### 5.4 UI, HUD, Menus & Buttons

#### ControlNet Wireframe Approach

For buttons and frames, draw a simple black-and-white wireframe box in MS Paint or any editor. Feed this into ControlNet (Canny or Scribble) to force the AI to fill in your pixel style exactly within your defined layout bounds.

```
[CLIP Text Encode] ─┐
[LayerDiffuse Alpha]─┼→ [KSampler] → [VAE Decode] → [Alpha Channel] → [Palette Match] → [Downscale] → [Save PNG]
[ControlNet: Canny] ─┘      ↑              ↑
                      [SD 1.5 Base]    [Wireframe.png]
                      [PixelArt LoRA]
```

**LayerDiffuse Settings:**
- Enable for all UI elements requiring transparency (buttons, icons, HUD frames)
- This generates a clean alpha channel, eliminating the need for manual background removal

#### 9-Patch Symmetry Enforcer Script

Save as `D:\GameProject\tools\enforce_9patch_symmetry.py`:

```python
from PIL import Image, ImageOps

def enforce_symmetry(input_path: str, output_path: str):
    """
    Mirrors the left half onto the right half, and the top onto the bottom,
    guaranteeing mathematically perfect symmetry for Godot's NinePatchRect.
    """
    img = Image.open(input_path).convert("RGBA")
    w, h = img.size

    # Mirror horizontally: use left half as master
    left_half = img.crop((0, 0, w // 2, h))
    right_half = ImageOps.mirror(left_half)
    img.paste(right_half, (w // 2, 0))

    # Mirror vertically: use top half as master
    top_half = img.crop((0, 0, w, h // 2))
    bottom_half = ImageOps.flip(top_half)
    img.paste(bottom_half, (0, h // 2))

    img.save(output_path)
    print(f"Symmetrical 9-patch saved to: {output_path}")


if __name__ == "__main__":
    import sys
    enforce_symmetry(sys.argv[1], sys.argv[2])
```

#### UI Asset Output Specifications

| Asset Type | Output Size | Format | Godot Node |
|---|---|---|---|
| Menu Background | 320×180 px (scaled to 1920×1080) | PNG | `TextureRect` |
| Dialog Box Frame | 128×64 px | PNG (with alpha) | `NinePatchRect` |
| Button (Normal) | 64×16 px | PNG (with alpha) | `TextureButton` |
| Button (Hover) | 64×16 px | PNG (with alpha) | `TextureButton` |
| Button (Pressed) | 64×16 px | PNG (with alpha) | `TextureButton` |
| HUD Icon | 16×16 px | PNG (with alpha) | `TextureRect` |
| Health Bar Frame | 64×8 px | PNG (with alpha) | `NinePatchRect` |

---

### 5.5 Normal Maps for 2D Lighting

Normal maps allow your flat pixel art to respond dynamically to Godot's `PointLight2D` nodes, creating depth, shadows, and highlights without 3D geometry.

#### Normal Map Generation Workflow

```
[Raw Albedo Sprite] → [GeoWizard / StableNormal Node] → [Normal Map Output]
                                                                 ↓
                                                    [Pixel Art Quantise Node]
                                                                 ↓
                                                    [Save as _normal.png]
```

Install the `ComfyUI-DepthAnything` or `ComfyUI-Marigold` node pack via ComfyUI Manager for the depth/normal estimation step.

**Naming Convention (critical for Godot auto-import):**
```
player_idle.png        ← Albedo (base color)
player_idle_normal.png ← Normal map (lighting depth)
```

**Normal Map Post-Process Settings:**
- Apply the same Nearest Neighbor downscale as the albedo
- Ensure normal map resolution exactly matches albedo resolution

---

## 6. Noise Removal & Reference Cleaning

Before feeding any AI concept art into a downstream generation workflow, it must be cleaned through this three-stage pipeline.

### 6.1 Install Python Dependencies

```bash
pip install pillow opencv-python scikit-learn numpy rembg
```

### 6.2 The Full Cleaning Pipeline Script

Save as `D:\GameProject\tools\clean_concept_reference.py`:

```python
import cv2
import numpy as np
from PIL import Image
from rembg import remove
from sklearn.cluster import KMeans
import json
import sys
import os

def remove_background(input_path: str, output_path: str):
    """Stage 1: Remove AI-generated background noise using BiRefNet via rembg."""
    with open(input_path, "rb") as f:
        input_data = f.read()
    output_data = remove(input_data)
    with open(output_path, "wb") as f:
        f.write(output_data)
    print(f"[Stage 1] Background removed: {output_path}")

def posterize_and_flatten(input_path: str, output_path: str, n_colors: int = 32):
    """
    Stage 2: K-Means color quantization to strip micro-gradients and
    compression artifacts that confuse Stable Diffusion.
    """
    img = Image.open(input_path).convert("RGBA")
    rgb = np.array(img)[:, :, :3]
    alpha = np.array(img)[:, :, 3]

    # Reshape for K-Means
    pixels = rgb.reshape(-1, 3).astype(np.float32)
    kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=10)
    kmeans.fit(pixels)

    # Replace each pixel with its cluster centroid
    quantized = kmeans.cluster_centers_[kmeans.labels_]
    quantized = quantized.reshape(rgb.shape).astype(np.uint8)

    # Reattach alpha channel
    result = np.dstack((quantized, alpha))
    Image.fromarray(result, "RGBA").save(output_path)
    print(f"[Stage 2] Color flattened to {n_colors} colors: {output_path}")

def apply_bilateral_filter(input_path: str, output_path: str):
    """Stage 3: Bilateral filter to smooth micro-noise while preserving hard edges."""
    img = cv2.imread(input_path, cv2.IMREAD_UNCHANGED)
    if img.shape[2] == 4:
        bgr = img[:, :, :3]
        alpha = img[:, :, 3]
        smoothed = cv2.bilateralFilter(bgr, d=9, sigmaColor=75, sigmaSpace=75)
        result = cv2.merge([smoothed, alpha])
    else:
        result = cv2.bilateralFilter(img, d=9, sigmaColor=75, sigmaSpace=75)
    cv2.imwrite(output_path, result)
    print(f"[Stage 3] Bilateral filter applied: {output_path}")

def extract_palette(input_path: str, palette_output_path: str, n_colors: int = 32):
    """Extract dominant colors as a palette PNG for ComfyUI Palette Match node."""
    img = Image.open(input_path).convert("RGB")
    pixels = np.array(img).reshape(-1, 3).astype(np.float32)
    kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init=10)
    kmeans.fit(pixels)
    palette_colors = kmeans.cluster_centers_.astype(np.uint8)

    # Create palette image (1×n_colors strip)
    palette_img = Image.fromarray(palette_colors.reshape(1, n_colors, 3), "RGB")
    palette_img = palette_img.resize((n_colors * 16, 16), Image.NEAREST)
    palette_img.save(palette_output_path)
    print(f"[Palette] Extracted {n_colors}-color palette: {palette_output_path}")

def full_clean_pipeline(input_path: str, output_dir: str, n_colors: int = 32):
    """Run the complete 3-stage cleaning pipeline on a concept art image."""
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(input_path))[0]

    stage1 = os.path.join(output_dir, f"{base}_stage1_nobg.png")
    stage2 = os.path.join(output_dir, f"{base}_stage2_flat.png")
    final  = os.path.join(output_dir, f"{base}_clean.png")
    palette = os.path.join(output_dir, f"{base}_palette.png")

    remove_background(input_path, stage1)
    posterize_and_flatten(stage1, stage2, n_colors)
    apply_bilateral_filter(stage2, final)
    extract_palette(final, palette, n_colors)

    print(f"\n✅ Cleaning complete. Use '{final}' as your IP-Adapter reference.")
    print(f"   Use '{palette}' as your Palette Match node input.")
    return final, palette


if __name__ == "__main__":
    input_img = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else "cleaned"
    n_colors   = int(sys.argv[3]) if len(sys.argv) > 3 else 32
    full_clean_pipeline(input_img, output_dir, n_colors)
```

**Usage:**
```bash
python tools/clean_concept_reference.py res/concepts/ranger_front.png res/concepts/cleaned/ 32
```

---

## 7. LoRA Training for Style Lock-In

A custom LoRA is the single most powerful method for enforcing a consistent art style. It bakes your visual identity directly into the neural network, so every asset generated — regardless of content — shares identical line weights, color relationships, and shading logic.

### 7.1 Install Kohya_ss (Local LoRA Trainer)

```bash
cd D:\AI
git clone https://github.com/bmaltais/kohya_ss.git
cd kohya_ss

# Run the Windows setup script
.\setup.bat
```

Follow the GUI installer. Kohya_ss will auto-detect your GPU and configure itself.

### 7.2 Prepare Your Training Dataset

You need **15–30 high-quality images** that perfectly represent your target style.

**Where to source your dataset:**
- Hand-selected screenshots from games with your target aesthetic (ensure they are from open-source or public domain games to avoid copyright issues)
- Your own hand-drawn pixel art sketches
- Public domain pixel art from [OpenGameArt.org](https://opengameart.org)
- Any mix of characters, environments, and UI that represents your style

**Dataset folder structure:**
```
D:\AI\kohya_ss\training_data\
    my_game_style\
        10_ProjectMyGameStyle\       ← "10" = repeat count
            image_01.png
            image_01.txt             ← Caption file
            image_02.png
            image_02.txt
            ...
```

**Caption file format (`image_01.txt`):**
```
ProjectMyGameStyle, a stone wall texture, dark grey bricks, mossy cracks, 
flat pixel art, limited color palette, retro game tileset
```

Every caption **must start with your unique style trigger token** (e.g., `ProjectMyGameStyle`). This is what Stable Diffusion will learn to associate with your style.

### 7.3 Training Configuration

In the Kohya_ss GUI, configure:

| Setting | Value |
|---|---|
| **Pretrained Model** | `sd_v1-5.safetensors` |
| **Training Data Dir** | `D:\AI\kohya_ss\training_data\my_game_style` |
| **Output Dir** | `D:\AI\ComfyUI\models\loras\` |
| **Output Name** | `my_game_style` |
| **Learning Rate** | `0.0001` |
| **Network Rank (Dim)** | `32` |
| **Network Alpha** | `16` |
| **Max Train Epochs** | `20` |
| **Batch Size** | `1` (for 12 GB VRAM) |
| **Resolution** | `512,512` |
| **Mixed Precision** | `fp16` |

Click **Train**. Training typically takes 30–90 minutes on an RTX 3060.

### 7.4 Verify LoRA Output

After training, your LoRA file will appear at:
`D:\AI\ComfyUI\models\loras\my_game_style.safetensors`

Test it in ComfyUI by loading the LoRA and prompting:
```
ProjectMyGameStyle, a health potion item icon
```

Compare the output to your training data. The style should match closely. If not, increase training epochs or add more varied training images.

---

## 8. Audio Asset Pipeline

### 8.1 Install AudioCraft (Meta's Open-Source Audio AI)

```bash
cd D:\AI
git clone https://github.com/facebookresearch/audiocraft.git
cd audiocraft
pip install -e .
```

### 8.2 Install Local TTS for Character Voices

For voice cloning and character grunts, install Fish Speech:

```bash
pip install fish-speech
```

Or Bark TTS:

```bash
pip install git+https://github.com/suno-ai/bark.git
```

### 8.3 Audio Generation Script

Save as `D:\GameProject\tools\generate_audio.py`:

```python
import subprocess
import json
import os
import sys

def generate_sfx_audiogen(prompt: str, output_path: str, duration: float = 1.0):
    """Generate a sound effect using AudioGen (Meta AudioCraft)."""
    script = f"""
import torchaudio
from audiocraft.models import AudioGen
from audiocraft.data.audio import audio_write

model = AudioGen.get_pretrained('facebook/audiogen-medium')
model.set_generation_params(duration={duration})
wav = model.generate(["{prompt}"])
audio_write('{os.path.splitext(output_path)[0]}', wav[0].cpu(), model.sample_rate, strategy="loudness")
"""
    with open("_temp_audiogen.py", "w") as f:
        f.write(script)
    subprocess.run(["python", "_temp_audiogen.py"])
    os.remove("_temp_audiogen.py")
    print(f"Generated SFX: {output_path}")


def generate_dialogue_bark(text: str, output_path: str):
    """Generate character speech and grunts using Bark TTS."""
    script = f"""
from bark import SAMPLE_RATE, generate_audio, preload_models
from scipy.io.wavfile import write as write_wav

preload_models()
audio = generate_audio("{text}")
write_wav("{output_path}", SAMPLE_RATE, audio)
"""
    with open("_temp_bark.py", "w") as f:
        f.write(script)
    subprocess.run(["python", "_temp_bark.py"])
    os.remove("_temp_bark.py")
    print(f"Generated dialogue: {output_path}")


# Example usage:
# generate_sfx_audiogen("short 8-bit retro synth blip, high pitch, triangle wave, video game menu click, clean", "res/audio/ui/menu_click.wav", 0.3)
# generate_dialogue_bark("[grunt] Hyah!", "res/audio/dialogue/hero_attack.wav")
```

---

## 9. Godot 4 Integration

### 9.1 Critical Rendering Settings

Open your Godot 4 project and go to **Project → Project Settings**. Set the following:

```
Rendering → Textures → Canvas Textures → Default Texture Filter → Nearest
```

Or directly in `project.godot`:
```ini
[rendering]
textures/canvas_textures/default_texture_filter=0
```

This is the **single most important Godot setting** for pixel art. Without it, Godot will blur all your crisp pixel assets when scaling.

### 9.2 Global SoundManager (Autoload)

Create `D:\GameProject\src\systems\SoundManager.gd` and register it as an **Autoload** in Project Settings:

```gdscript
# SoundManager.gd - Global Audio Manager
# Register this as an Autoload singleton in Project Settings → Autoload
extends Node

var ui_sounds: Dictionary = {
    "click":   preload("res://audio/ui/button_click.wav"),
    "hover":   preload("res://audio/ui/menu_hover.wav"),
    "back":    preload("res://audio/ui/menu_back.wav"),
    "confirm": preload("res://audio/ui/menu_confirm.wav"),
    "error":   preload("res://audio/ui/menu_error.wav"),
}

var foley_sounds: Dictionary = {
    "grass_step":  [
        preload("res://audio/foley/grass_step_01.wav"),
        preload("res://audio/foley/grass_step_02.wav"),
        preload("res://audio/foley/grass_step_03.wav"),
    ],
    "stone_step": [
        preload("res://audio/foley/stone_step_01.wav"),
        preload("res://audio/foley/stone_step_02.wav"),
    ],
}

func _ready() -> void:
    get_tree().node_added.connect(_on_node_added)

func _on_node_added(node: Node) -> void:
    if node is Button:
        node.mouse_entered.connect(func(): play_ui("hover"))
        node.pressed.connect(func(): play_ui("click"))

func play_ui(sound_name: String) -> void:
    if not ui_sounds.has(sound_name):
        return
    var player := AudioStreamPlayer.new()
    add_child(player)
    player.stream = ui_sounds[sound_name]
    player.bus = "UI"
    player.play()
    player.finished.connect(player.queue_free)

func play_foley(category: String) -> void:
    if not foley_sounds.has(category):
        return
    var variants: Array = foley_sounds[category]
    var player := AudioStreamPlayer2D.new()
    add_child(player)
    player.stream = variants.pick_random()
    player.pitch_scale = randf_range(0.85, 1.15)
    player.bus = "GameWorld"
    player.play()
    player.finished.connect(player.queue_free)
```

### 9.3 Master Animation Controller

Create `D:\GameProject\src\systems\MasterAnimationClock.gd`:

```gdscript
# MasterAnimationClock.gd
# Attach to any entity using AnimatedSprite2D to enforce unified FPS
extends AnimatedSprite2D

## Shared animation FPS across all game entities.
## 12 = classic retro feel. 24 = modern smooth pixel art.
const MASTER_FPS: int = 12

func _ready() -> void:
    _apply_master_fps()

func _apply_master_fps() -> void:
    if sprite_frames == null:
        return
    for anim_name in sprite_frames.get_animation_names():
        sprite_frames.set_animation_speed(anim_name, MASTER_FPS)

func play_with_speed(anim_name: String, speed_scale_override: float = 1.0) -> void:
    speed_scale = speed_scale_override
    play(anim_name)
```

### 9.4 Dialogue Text-Crawl Controller

Create `D:\GameProject\src\systems\DialogueController.gd`:

```gdscript
# DialogueController.gd - Procedural text crawl with per-letter audio blips
extends RichTextLabel

@export var blip_sound: AudioStream
@export var text_speed: float = 0.04  # seconds per character
@onready var audio_player: AudioStreamPlayer = $AudioStreamPlayer

signal dialogue_finished

func speak(new_text: String) -> void:
    text = new_text
    visible_characters = 0

    for i in range(text.length()):
        visible_characters += 1
        var ch: String = text[i]

        if ch != " " and ch != "\n" and blip_sound:
            audio_player.pitch_scale = randf_range(0.9, 1.1)
            audio_player.stream = blip_sound
            audio_player.play()

        var delay: float = text_speed
        if ch in [".", "!", "?"]:
            delay = text_speed * 8.0  # Pause at sentence ends
        elif ch == ",":
            delay = text_speed * 3.0

        await get_tree().create_timer(delay).timeout

    emit_signal("dialogue_finished")
```

### 9.5 Animation-Audio Sync Script

Create `D:\GameProject\src\systems\AnimationAudioSyncer.gd`:

```gdscript
# AnimationAudioSyncer.gd
# Programmatically adds audio trigger keyframes to AnimationPlayer tracks.
# Use via Claude Code to avoid manual editor work.
extends Node

func add_audio_trigger(
    anim_player: AnimationPlayer,
    anim_name: String,
    time_stamp: float,
    method_name: String,
    args: Array = []
) -> void:
    if not anim_player.has_animation(anim_name):
        push_error("Animation not found: " + anim_name)
        return

    var anim: Animation = anim_player.get_animation(anim_name)
    var track_idx: int = anim.add_track(Animation.TYPE_METHOD)
    anim.track_set_path(track_idx, NodePath("."))
    anim.method_track_insert_key(track_idx, time_stamp, {
        "method": method_name,
        "args": args
    })
    print("Audio trigger added: %s at %.2fs on '%s'" % [method_name, time_stamp, anim_name])
```

### 9.6 Retro 2D Lighting Shader

Save as `D:\GameProject\src\shaders\retro_pixel_lighting.gdshader`:

```glsl
shader_type canvas_item;

uniform sampler2D normal_map : hint_normal, filter_nearest;
uniform float light_strength : hint_range(0.0, 2.0) = 1.0;
uniform int shadow_steps : hint_range(2, 8) = 4;
uniform vec4 ambient_color : source_color = vec4(0.1, 0.1, 0.2, 1.0);

void fragment() {
    vec4 albedo = texture(TEXTURE, UV);
    vec3 normal = texture(normal_map, UV).rgb;
    
    // Convert from [0,1] to [-1,1] range
    normal = normalize(normal * 2.0 - 1.0);
    
    // LIGHT is a built-in Godot canvas_item variable when PointLight2D is present
    float diffuse = max(dot(normal, vec3(0.0, 0.0, 1.0)), 0.0);
    
    // Posterize the lighting into discrete steps (retro dither effect)
    diffuse = floor(diffuse * float(shadow_steps)) / float(shadow_steps);
    
    vec3 lit = albedo.rgb * (ambient_color.rgb + diffuse * light_strength);
    COLOR = vec4(lit, albedo.a);
}
```

Apply this shader to a `ShaderMaterial` on any `CanvasTexture` that has both an albedo and a normal map assigned.

---

## 10. Claude Code Integration

### 10.1 Install Claude Code

```bash
npm install -g @anthropic-ai/claude-code
```

Verify:
```bash
claude --version
```

### 10.2 The Central Asset Factory Script

Save as `D:\GameProject\generate_factory.py`:

```python
"""
generate_factory.py
Central bridge between Claude Code and the local ComfyUI API.
Run via: python generate_factory.py --mode <MODE> --prompt "<PROMPT>" --output "<OUTPUT_PATH>"
"""

import json
import time
import uuid
import urllib.request
import urllib.parse
import argparse
import os
import websocket


# ─────────────────────────────────────────────────────────────────────
# Load project config
# ─────────────────────────────────────────────────────────────────────
with open("style_config.json", "r") as f:
    CONFIG = json.load(f)

COMFYUI_URL = CONFIG["comfyui_api_url"]
CLIENT_ID    = str(uuid.uuid4())


def load_workflow(workflow_path: str) -> dict:
    with open(workflow_path, "r") as f:
        return json.load(f)


def inject_prompt_into_workflow(workflow: dict, positive_prompt: str, negative_prompt: str = None) -> dict:
    """
    Finds CLIP Text Encode nodes in the workflow and injects your prompts.
    Automatically appends your global style anchors from style_config.json.
    """
    global_positive = ", ".join(CONFIG["positive_anchors"])
    global_negative  = ", ".join(CONFIG["negative_anchors"])

    full_positive = f"{global_positive}, {positive_prompt}"
    full_negative  = negative_prompt or global_negative

    for node_id, node in workflow.items():
        if node.get("class_type") == "CLIPTextEncode":
            current_text = node["inputs"].get("text", "")
            if "POSITIVE_PLACEHOLDER" in current_text:
                node["inputs"]["text"] = full_positive
            elif "NEGATIVE_PLACEHOLDER" in current_text:
                node["inputs"]["text"] = full_negative

    return workflow


def queue_prompt(workflow: dict) -> str:
    """Send workflow to ComfyUI and return the prompt_id."""
    payload = json.dumps({"prompt": workflow, "client_id": CLIENT_ID}).encode("utf-8")
    req = urllib.request.Request(f"{COMFYUI_URL}/prompt", data=payload)
    response = urllib.request.urlopen(req)
    return json.loads(response.read())["prompt_id"]


def wait_for_completion(prompt_id: str) -> None:
    """Poll ComfyUI via WebSocket until the generation is complete."""
    ws = websocket.WebSocket()
    ws.connect(f"ws://{COMFYUI_URL.replace('http://', '')}/ws?clientId={CLIENT_ID}")
    print(f"Waiting for generation (prompt_id: {prompt_id[:8]}...)...")
    while True:
        out = ws.recv()
        if isinstance(out, str):
            msg = json.loads(out)
            if msg["type"] == "executing" and msg["data"].get("prompt_id") == prompt_id:
                if msg["data"]["node"] is None:
                    print("✅ Generation complete.")
                    break
    ws.close()


def get_output_images(prompt_id: str) -> list:
    """Retrieve the output image filenames from ComfyUI's history."""
    req = urllib.request.urlopen(f"{COMFYUI_URL}/history/{prompt_id}")
    history = json.loads(req.read())
    images = []
    for node_output in history[prompt_id]["outputs"].values():
        if "images" in node_output:
            images.extend(node_output["images"])
    return images


def download_image(filename: str, subfolder: str, output_path: str) -> None:
    """Download a generated image from ComfyUI and save to the Godot project folder."""
    params = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
    req = urllib.request.urlopen(f"{COMFYUI_URL}/view?{params}")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(req.read())
    print(f"💾 Saved to: {output_path}")


def generate_asset(mode: str, prompt: str, output_path: str, reference_image: str = None) -> None:
    """
    Main generation function.
    Modes:
        concept     → High-res concept art using SDXL
        character   → Pixel sprite sheet with IP-Adapter + ControlNet
        terrain     → Seamlessly tiling terrain texture
        ui          → UI element with transparency (LayerDiffuse)
        normal_map  → Normal map from an existing albedo image
        animation   → AnimateDiff sprite sheet
    """
    workflow_map = {
        "concept":    "workflows/concept_art.json",
        "character":  "workflows/character_sprite.json",
        "terrain":    "workflows/terrain_tile.json",
        "ui":         "workflows/ui_element.json",
        "normal_map": "workflows/normal_map.json",
        "animation":  "workflows/animation_sheet.json",
    }

    if mode not in workflow_map:
        print(f"Unknown mode: {mode}. Valid modes: {list(workflow_map.keys())}")
        return

    print(f"🎨 Mode: {mode} | Prompt: {prompt[:60]}...")
    workflow = load_workflow(workflow_map[mode])
    workflow = inject_prompt_into_workflow(workflow, prompt)

    prompt_id = queue_prompt(workflow)
    wait_for_completion(prompt_id)

    images = get_output_images(prompt_id)
    if images:
        img = images[0]
        download_image(img["filename"], img["subfolder"], output_path)
    else:
        print("⚠️  No images returned from ComfyUI.")


# ─────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Game Asset Factory")
    parser.add_argument("--mode",      required=True, help="Asset type to generate")
    parser.add_argument("--prompt",    required=True, help="Generation prompt")
    parser.add_argument("--output",    required=True, help="Output file path")
    parser.add_argument("--reference", default=None,  help="Reference image path for IP-Adapter")
    args = parser.parse_args()

    generate_asset(args.mode, args.prompt, args.output, args.reference)
```

Install the websocket dependency:
```bash
pip install websocket-client
```

### 10.3 Example Claude Code Prompts

With this pipeline running, you can instruct Claude Code naturally from the terminal:

```
"Claude, generate concept art of a forest ranger character with green 
 armor and a wooden bow. Save it to res/concepts/characters/ranger.png."
```

```
"Claude, clean the concept art at res/concepts/characters/ranger.png 
 and extract the color palette, then update our style_config.json."
```

```
"Claude, generate a 32x32 seamless moss stone floor tile using the 
 cleaned ranger concept as IP-Adapter reference and save it to 
 res/art/terrain/moss_stone.png."
```

```
"Claude, generate a normal map for res/art/terrain/moss_stone.png 
 and save it as res/art/terrain/moss_stone_normal.png."
```

```
"Claude, run the auto-centering script on res/art/sprites/raw/player_walk_raw.png 
 with a 32px cell size and save the result to res/art/sprites/player_walk.png."
```

---

## 11. Project Folder Structure

```
D:\GameProject\
│
├── generate_factory.py          ← Main Claude Code ↔ ComfyUI bridge
├── style_config.json            ← Master style configuration
├── launch_comfyui.bat           ← Launches the ComfyUI API server
│
├── style\
│   ├── master_palette.png       ← Project-wide locked color palette
│   ├── style_anchor.png         ← First approved asset (IP-Adapter master)
│   └── skeletons\               ← OpenPose skeleton template sheets
│       ├── walk_8frame.png
│       ├── jump_3frame.png
│       └── attack_4frame.png
│
├── tools\
│   ├── clean_concept_reference.py
│   ├── center_sprite_sheet.py
│   ├── enforce_9patch_symmetry.py
│   └── generate_audio.py
│
├── workflows\                   ← ComfyUI workflow JSON exports (API format)
│   ├── concept_art.json
│   ├── character_sprite.json
│   ├── terrain_tile.json
│   ├── ui_element.json
│   ├── normal_map.json
│   └── animation_sheet.json
│
└── res\                         ← Godot project root
    ├── project.godot
    ├── concepts\                ← Raw & cleaned concept art (reference only)
    │   ├── characters\
    │   ├── environments\
    │   ├── ui\
    │   └── cleaned\
    ├── art\
    │   ├── sprites\             ← Character sprite sheets
    │   ├── terrain\             ← Seamless tiles and normal maps
    │   └── ui\                  ← Buttons, frames, HUD icons (with alpha)
    ├── audio\
    │   ├── dialogue\            ← Voice-cloned character lines
    │   ├── foley\               ← Movement sound variants
    │   └── ui\                  ← Menu blips, clicks, feedback sounds
    └── src\
        ├── actors\              ← Player, enemy scripts
        ├── systems\             ← SoundManager.gd, DialogueController.gd, etc.
        └── shaders\             ← retro_pixel_lighting.gdshader, ui_glow.gdshader
```

---

## 12. Style Config Reference

### Quick Checklist Before Generating Any Asset

- [ ] `launch_comfyui.bat` is running (ComfyUI accessible at port 8188)
- [ ] `style_config.json` has your current style trigger token
- [ ] `master_palette.png` is loaded in your workflow's Palette Match node
- [ ] Your custom LoRA (`my_game_style.safetensors`) is loaded in your workflow
- [ ] IP-Adapter node has `style_anchor.png` assigned
- [ ] Downscale node is set to **Nearest Neighbor** filter
- [ ] Godot's `Default Texture Filter` is set to **Nearest**

### Style Enforcement Layer Summary

| Layer | Tool | What It Locks |
|---|---|---|
| **1. Neural Style** | Custom LoRA (Kohya_ss) | Line weight, shading logic, aesthetic values |
| **2. Color Palette** | Palette Match Node + master_palette.png | All hex color values, no color drift between assets |
| **3. Composition** | IP-Adapter + style_anchor.png | Shape proportions, outfit geometry, structural feel |
| **4. Motion Structure** | ControlNet OpenPose | Limb positions, stride length, animation arc |
| **5. Resolution Grid** | Nearest Neighbor Downscale | Pixel grid size, no sub-pixel blurring |
| **6. Engine Rendering** | Godot Nearest Filter + Shaders | Final display consistency, unified lighting math |
| **7. Audio Texture** | Godot Bitcrusher Audio Bus | Retro digital crunch matching pixel art depth |

When all seven layers are active, it becomes mathematically impossible for any generated asset — whether a dungeon tile, a character grunt, or a menu button — to feel out of place in your game.

---

## 13. Music Generation Pipeline

This section extends the asset factory with a fully local, open-source AI music pipeline. The goal is to compose an orchestral game soundtrack that maintains a **single leitmotif** across every environment — title screen, town, snow area, desert, combat — while ensuring every track loops seamlessly and sounds like it belongs to the same sonic world.

The core design principle mirrors the visual pipeline: **lock the structural DNA first, then let the AI fill in the details**.

---

### 13.1 Music Stack Overview

```
[ Your Core Melody (MIDI / Audio) ]
              │
              ▼
[ Layer 1: SYMBOLIC COMPOSITION ]
  MusPy / pretty_midi (Python)
  → Transpose melody into biome scales
  → Augment / fragment notes for subtlety
  → Export per-biome .mid files
              │
              ▼
[ Layer 2: AUDIO SYNTHESIS ]
  Meta AudioCraft — MusicGen-Melody (local)
  → Accepts melody audio + text prompt
  → Renders full orchestral stems per biome
              │
              ▼
[ Layer 3: POST-PROCESSING & LOOPING ]
  Audacity (CLI macro) / REAPER (SWS scripts)
  → Apply shared IR convolution reverb
  → Apply global EQ profile
  → Engineer seamless loops (split-and-glue)
              │
              ▼
[ Layer 4: GAME INTEGRATION ]
  Godot 4 AudioStreamPlayer + GDScript
  → Crossfade environment stems dynamically
  → Randomly surface leitmotif melody layer
  → Procedural pitch variation per playback
```

**Hardware requirements for music pipeline:**

| Component | Minimum | Recommended |
|---|---|---|
| GPU VRAM | 8 GB | 12–16 GB |
| RAM | 16 GB | 32 GB |
| Storage | +20 GB | +40 GB |
| Python | 3.10.x | 3.10.11 |

> The music pipeline shares the same Python environment as the visual pipeline. No additional Python installation is needed.

---

### 13.2 Installation: Music Tools

#### Install AudioCraft (MusicGen-Melody)

AudioCraft is Meta's open-source suite. `MusicGen-Melody` is the specific model that accepts both a melody audio file and a text prompt simultaneously — the critical feature for leitmotif conditioning.

```bash
cd D:\AI
git clone https://github.com/facebookresearch/audiocraft.git
cd audiocraft

# Install in editable mode
pip install -e .

# Download the MusicGen-Melody model weights (~2.5 GB)
python -c "from audiocraft.models import MusicGen; MusicGen.get_pretrained('facebook/musicgen-melody')"
```

#### Install LMMS (Free DAW for Melody Authoring)

LMMS is a fully open-source digital audio workstation used to write and export your core melody as a MIDI file.

Download from [https://lmms.io/download](https://lmms.io/download) and install with default settings.

#### Install MusPy and pretty_midi (Symbolic Music Libraries)

These Python libraries allow you to programmatically manipulate MIDI files — transposing scales, augmenting note durations, fragmenting phrases — without touching a DAW.

```bash
pip install muspy pretty_midi scipy soundfile
```

#### Install Audacity (CLI-capable audio editor)

Audacity is used for batch post-processing — applying EQ, reverb, and normalization to all AI-generated stems.

Download from [https://www.audacityteam.org/download/](https://www.audacityteam.org/download/)

Enable the scripting interface by going to **Edit → Preferences → Modules** and enabling `mod-script-pipe`.

---

### 13.3 Layer 1 — Symbolic Composition (The Brain)

This layer is the foundation of leitmotif consistency. **Never rely on the audio AI to remember your melody between generations.** All melodic transformations — scale changes, note augmentation, phrase fragmentation — happen here at the MIDI level before any audio is generated.

#### Step 1: Write and Export Your Core Melody

In LMMS:
1. Open the **Beat + Bassline Editor** or **Piano Roll**
2. Compose your leitmotif — 4 to 8 bars is ideal
3. Keep it simple: a memorable 6–10 note phrase works best
4. Export via **File → Export → MIDI** → save as `D:\GameProject\music\leitmotif_core.mid`

Also export an audio render: **File → Export → WAV** → save as `D:\GameProject\music\leitmotif_core.wav`

The `.wav` file is what you feed into MusicGen-Melody. The `.mid` file is what you manipulate programmatically.

#### Step 2: The Leitmotif Transformation Script

Save as `D:\GameProject\music\tools\transform_leitmotif.py`:

```python
"""
transform_leitmotif.py
Transforms your core leitmotif MIDI into per-biome variations
by shifting scales, augmenting durations, and fragmenting phrases.

Usage:
    python transform_leitmotif.py --input leitmotif_core.mid --biome snow
"""

import pretty_midi
import numpy as np
import argparse
import os

# ─────────────────────────────────────────────────────────
# Scale interval maps (semitone offsets from root note)
# ─────────────────────────────────────────────────────────
SCALES = {
    "major":           [0, 2, 4, 5, 7, 9, 11],  # Bright, heroic (title/town)
    "natural_minor":   [0, 2, 3, 5, 7, 8, 10],  # Sad, reflective (caves, ruins)
    "harmonic_minor":  [0, 2, 3, 5, 7, 8, 11],  # Exotic tension (desert, boss)
    "phrygian":        [0, 1, 3, 5, 7, 8, 10],  # Dark, mysterious (dungeons)
    "dorian":          [0, 2, 3, 5, 7, 9, 10],  # Folk, ancient (forest, ruins)
    "pentatonic_major":[0, 2, 4, 7, 9],          # Open, vast (snow, sky)
    "pentatonic_minor":[0, 3, 5, 7, 10],         # Brooding, heavy (swamp, void)
    "lydian":          [0, 2, 4, 6, 7, 9, 11],  # Dreamy, magical (fairy areas)
}

# ─────────────────────────────────────────────────────────
# Per-biome transformation presets
# ─────────────────────────────────────────────────────────
BIOME_PRESETS = {
    "title": {
        "scale":           "major",
        "tempo_multiplier": 1.0,
        "augment_factor":  1.0,   # Full melody, no changes
        "fragment":        False, # Play all notes
        "transpose":       0,     # No transposition
        "description":     "Full leitmotif, major key, definitive form"
    },
    "town": {
        "scale":           "major",
        "tempo_multiplier": 0.9,
        "augment_factor":  1.2,   # Slightly slower notes (more lyrical)
        "fragment":        False,
        "transpose":       0,
        "description":     "Soft, slower, same key — comfortable and familiar"
    },
    "snow": {
        "scale":           "pentatonic_major",
        "tempo_multiplier": 0.65,
        "augment_factor":  2.0,   # Double note lengths (half-speed feel)
        "fragment":        True,  # Keep only first 3 notes (echo effect)
        "transpose":       5,     # Up a 4th (higher register = icy, distant)
        "description":     "Sparse echo of motif, high register, slow and cold"
    },
    "desert": {
        "scale":           "harmonic_minor",
        "tempo_multiplier": 1.15,
        "augment_factor":  0.85,  # Slightly clipped notes (staccato feel)
        "fragment":        False,
        "transpose":       -2,    # Down a step (lower, heavier)
        "description":     "Full motif bent into harmonic minor — exotic and tense"
    },
    "forest": {
        "scale":           "dorian",
        "tempo_multiplier": 0.95,
        "augment_factor":  1.1,
        "fragment":        False,
        "transpose":       2,
        "description":     "Ancient folk feel, warm and organic"
    },
    "dungeon": {
        "scale":           "phrygian",
        "tempo_multiplier": 0.75,
        "augment_factor":  1.5,
        "fragment":        True,  # Only first half of phrase
        "transpose":       -5,    # Down a 4th (dark, low)
        "description":     "Dark and ominous — melody barely recognizable"
    },
    "combat": {
        "scale":           "harmonic_minor",
        "tempo_multiplier": 1.4,  # Fast and aggressive
        "augment_factor":  0.5,   # Short, punchy notes
        "fragment":        False,
        "transpose":       0,
        "description":     "Same harmonic content, double speed — high intensity"
    },
    "boss": {
        "scale":           "phrygian",
        "tempo_multiplier": 1.2,
        "augment_factor":  0.6,
        "fragment":        False,
        "transpose":       -7,    # Down a 5th (massive, threatening)
        "description":     "Full motif, darkest scale, low register — maximum menace"
    },
}


def snap_to_scale(pitch: int, scale_intervals: list, root: int = 60) -> int:
    """Snap a MIDI pitch to the nearest note in the target scale."""
    octave_offset = (pitch - root) // 12
    pitch_class    = (pitch - root) % 12
    closest        = min(scale_intervals, key=lambda x: abs(x - pitch_class))
    return root + octave_offset * 12 + closest


def transform_midi(input_path: str, biome: str, output_dir: str) -> str:
    """Apply biome-specific transformations to the core leitmotif MIDI."""
    if biome not in BIOME_PRESETS:
        raise ValueError(f"Unknown biome: '{biome}'. Choose from: {list(BIOME_PRESETS.keys())}")

    preset  = BIOME_PRESETS[biome]
    midi    = pretty_midi.PrettyMIDI(input_path)
    scale   = SCALES[preset["scale"]]
    root    = 60  # Middle C as the tonal root

    # Adjust global tempo
    for i, tempo in enumerate(midi.get_tempo_change_times()):
        pass  # pretty_midi handles tempo internally; we scale note times

    new_midi = pretty_midi.PrettyMIDI(initial_tempo=120 * preset["tempo_multiplier"])

    for instrument in midi.instruments:
        new_instrument = pretty_midi.Instrument(program=instrument.program, is_drum=instrument.is_drum)
        notes          = instrument.notes

        # Fragment: keep only the first N notes if enabled
        if preset["fragment"]:
            notes = notes[:max(3, len(notes) // 2)]

        for note in notes:
            # Scale tempo
            start = note.start / preset["tempo_multiplier"]
            end   = note.start / preset["tempo_multiplier"] + (note.end - note.start) * preset["augment_factor"]

            # Transpose and snap to target scale
            new_pitch = snap_to_scale(note.pitch + preset["transpose"], scale, root)
            new_pitch = max(21, min(108, new_pitch))  # Stay within MIDI piano range

            new_note = pretty_midi.Note(
                velocity=note.velocity,
                pitch=new_pitch,
                start=start,
                end=end,
            )
            new_instrument.notes.append(new_note)

        new_midi.instruments.append(new_instrument)

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"leitmotif_{biome}.mid")
    new_midi.write(output_path)
    print(f"✅ [{biome.upper()}] {preset['description']}")
    print(f"   Saved: {output_path}")
    return output_path


def batch_transform(input_path: str, output_dir: str) -> None:
    """Generate MIDI variations for all biomes at once."""
    print(f"\n🎵 Transforming leitmotif for all biomes...\n{'─'*50}")
    for biome in BIOME_PRESETS:
        transform_midi(input_path, biome, output_dir)
    print(f"\n✅ All biome MIDI files saved to: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Leitmotif Transformer")
    parser.add_argument("--input",  required=True, help="Path to core leitmotif .mid file")
    parser.add_argument("--biome",  default="all",  help="Biome name, or 'all' for batch")
    parser.add_argument("--output", default="D:/GameProject/music/midi_variations/")
    args = parser.parse_args()

    if args.biome == "all":
        batch_transform(args.input, args.output)
    else:
        transform_midi(args.input, args.biome, args.output)
```

**Batch usage (generate all biome MIDIs at once):**
```bash
cd D:\GameProject
python music\tools\transform_leitmotif.py --input music\leitmotif_core.mid --biome all
```

This produces a set of MIDI files in `music\midi_variations\`, each a musically valid transformation of your core melody. These MIDI files are then rendered to audio in Layer 2.

---

### 13.4 Layer 2 — Audio Synthesis (The Orchestra)

This layer takes the per-biome MIDI variations and your core melody audio file, feeds them into MusicGen-Melody alongside structured text prompts, and renders full orchestral stems.

#### The Locked Prompt Architecture

The single most important consistency tool in audio generation is **programmatic prompt anchoring**. Your prompts are split into two parts that never mix:

- **`core_sonic_identity`** — identical across every single generation; defines the shared "sound" of your game's soundtrack
- **`biome_modifier`** — changes per biome; defines the specific emotional texture

#### The Music Generation Script

Save as `D:\GameProject\music\tools\generate_music.py`:

```python
"""
generate_music.py
Generates orchestral game music stems using MusicGen-Melody.
Each biome gets its own stem while sharing the same core sonic identity.

Usage:
    python generate_music.py --biome snow
    python generate_music.py --biome all
"""

import torch
import torchaudio
import soundfile as sf
import numpy as np
import argparse
import os
from audiocraft.models import MusicGen
from audiocraft.data.audio import audio_write

# ─────────────────────────────────────────────────────────
# LOCKED SONIC IDENTITY — never change this between biomes.
# This is what makes every track sound like the same game.
# ─────────────────────────────────────────────────────────
CORE_SONIC_IDENTITY = (
    "orchestral video game soundtrack, live acoustic instruments, "
    "warm string ensemble, recorded in a wooden concert hall, "
    "high fidelity master, cinematic depth, no electronic synthesizers, "
    "no drum machines, cohesive harmonic language"
)

# ─────────────────────────────────────────────────────────
# Per-biome modifiers — only the texture and emotion change.
# ─────────────────────────────────────────────────────────
BIOME_PROMPTS = {
    "title": (
        "sweeping cinematic title theme, full orchestra, majestic brass fanfare, "
        "soaring violin melody, triumphant 4/4 tempo 90 BPM, grand and memorable"
    ),
    "town": (
        "peaceful village theme, solo acoustic guitar, light woodwinds, "
        "gentle pizzicato strings, 80 BPM, warm and nostalgic, safe and welcoming"
    ),
    "snow": (
        "frozen tundra ambient, solo celesta, distant high register strings, "
        "sparse and minimal, 60 BPM, cold isolated atmosphere, vast and empty, "
        "sparse notes with long silences between phrases"
    ),
    "desert": (
        "arid desert theme, ethnic middle eastern strings, heavy hand percussion, "
        "droning low cello, 110 BPM, exotic and harsh, shimmering heat effect, "
        "driving rhythmic pulse"
    ),
    "forest": (
        "ancient forest theme, solo oboe, warm french horn, "
        "rustling string textures, 85 BPM, organic and mysterious, "
        "folk-like melodic phrasing"
    ),
    "dungeon": (
        "dark dungeon ambient, low register cellos, ominous bassoon, "
        "sustained minor cluster chords, 55 BPM, tension and dread, "
        "sparse, oppressive silence between phrases"
    ),
    "combat": (
        "intense battle music, aggressive staccato strings, full brass, "
        "driving timpani, 140 BPM, adrenaline, relentless rhythmic drive, "
        "short sharp note attacks"
    ),
    "boss": (
        "final boss theme, massive low brass, thunderous timpani, "
        "dissonant string clusters, choir hits, 120 BPM, "
        "overwhelming and menacing, full orchestral force"
    ),
}

# Generation length in seconds — choose a value that divides cleanly into BPM bars
# 60 BPM × 4 bars × 4/4 = 64 seconds. Stick to 32 or 64 seconds for clean loops.
BIOME_DURATION = {
    "title":   64,
    "town":    32,
    "snow":    64,
    "desert":  32,
    "forest":  64,
    "dungeon": 64,
    "combat":  32,
    "boss":    64,
}


def load_model() -> MusicGen:
    print("🎼 Loading MusicGen-Melody model...")
    model = MusicGen.get_pretrained("facebook/musicgen-melody")
    model.set_generation_params(
        use_sampling=True,
        top_k=250,
        top_p=0.0,
        temperature=1.0,
        cfg_coef=3.0,     # Classifier-free guidance: higher = more faithful to prompt
    )
    return model


def load_melody_wav(melody_path: str, sample_rate: int = 32000) -> torch.Tensor:
    """Load the biome-specific melody WAV (rendered from MIDI) for conditioning."""
    waveform, sr = torchaudio.load(melody_path)
    if sr != sample_rate:
        waveform = torchaudio.functional.resample(waveform, sr, sample_rate)
    # MusicGen-Melody expects shape [batch, channels, time]
    return waveform.unsqueeze(0)


def generate_stem(model: MusicGen, biome: str, melody_dir: str, output_dir: str) -> None:
    """Generate one orchestral stem for the given biome."""
    if biome not in BIOME_PROMPTS:
        raise ValueError(f"Unknown biome: '{biome}'. Options: {list(BIOME_PROMPTS.keys())}")

    melody_path = os.path.join(melody_dir, f"leitmotif_{biome}.wav")
    if not os.path.exists(melody_path):
        raise FileNotFoundError(
            f"Melody WAV not found: {melody_path}\n"
            f"Render your MIDI variation to WAV first using LMMS or FluidSynth."
        )

    full_prompt = f"{CORE_SONIC_IDENTITY}, {BIOME_PROMPTS[biome]}"
    duration    = BIOME_DURATION[biome]

    print(f"\n🎵 Generating [{biome.upper()}] ({duration}s)...")
    print(f"   Prompt: {full_prompt[:80]}...")

    model.set_generation_params(duration=duration)
    melody_wav = load_melody_wav(melody_path)

    # Generate with melody conditioning
    wav = model.generate_with_chroma(
        descriptions=[full_prompt],
        melody_wavs=melody_wav,
        melody_sample_rate=32000,
        progress=True,
    )

    os.makedirs(output_dir, exist_ok=True)
    output_stem = os.path.join(output_dir, f"{biome}_raw")
    audio_write(output_stem, wav[0].cpu(), model.sample_rate, strategy="loudness")
    print(f"   ✅ Saved: {output_stem}.wav")


def batch_generate(model: MusicGen, melody_dir: str, output_dir: str) -> None:
    print(f"\n🎼 Generating all biome stems...\n{'─'*50}")
    for biome in BIOME_PROMPTS:
        try:
            generate_stem(model, biome, melody_dir, output_dir)
        except FileNotFoundError as e:
            print(f"   ⚠️  Skipping {biome}: {e}")
    print(f"\n✅ All stems saved to: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Music Generator")
    parser.add_argument("--biome",       default="all")
    parser.add_argument("--melody_dir",  default="D:/GameProject/music/midi_variations/wav/")
    parser.add_argument("--output_dir",  default="D:/GameProject/music/stems_raw/")
    args = parser.parse_args()

    model = load_model()
    if args.biome == "all":
        batch_generate(model, args.melody_dir, args.output_dir)
    else:
        generate_stem(model, args.biome, args.melody_dir, args.output_dir)
```

> **Note on MIDI → WAV conversion:** MusicGen-Melody requires audio, not MIDI. To convert your transformed MIDI files to WAV, use FluidSynth (free, open-source) with a General MIDI soundfont:
>
> ```bash
> # Install FluidSynth
> winget install FluidSynth.FluidSynth
>
> # Convert a MIDI to WAV using a soundfont
> fluidsynth -ni soundfont.sf2 music/midi_variations/leitmotif_snow.mid -F music/midi_variations/wav/leitmotif_snow.wav -r 44100
> ```
>
> Download a high-quality free soundfont such as `GeneralUser GS` from [https://schristiancollins.com/generaluser.php](https://schristiancollins.com/generaluser.php).

---

### 13.5 Layer 3 — Post-Processing & Looping (The Studio)

Raw AI audio outputs will have mismatched room acoustics, varying loudness, and no clean loop point. This layer standardizes every stem before it enters Godot.

#### Audacity CLI Batch Processing

Save as `D:\GameProject\music\tools\process_stems.py`:

```python
"""
process_stems.py
Batch-processes raw AI music stems via Audacity's scripting pipe.
Applies: normalization → EQ profile → IR reverb → loop engineering → export.

Requires Audacity with mod-script-pipe enabled.
"""

import socket
import time
import os
import glob

PIPE_IN  = r"\\.\pipe\ToSrvPipe"
PIPE_OUT = r"\\.\pipe\FromSrvPipe"


def send_command(cmd: str, timeout: float = 30.0) -> str:
    """Send a command to Audacity via scripting pipe and return the response."""
    try:
        with open(PIPE_IN, "w") as pipe_in:
            pipe_in.write(cmd + "\n")
        time.sleep(0.3)
        with open(PIPE_OUT, "r") as pipe_out:
            return pipe_out.readline().strip()
    except Exception as e:
        return f"Error: {e}"


def process_stem(input_wav: str, output_wav: str) -> None:
    """Apply the full standardization chain to a single stem."""
    print(f"  Processing: {os.path.basename(input_wav)}")

    # Import file
    send_command(f'Import2: Filename="{input_wav}"')
    time.sleep(1.0)

    # 1. Normalize to -3 dB (consistent loudness across all stems)
    send_command("Normalize: PeakLevel=-3 ApplyGain=1 StereoIndependent=0")

    # 2. Global EQ: cut sub-bass rumble, tame harsh highs
    #    This makes all stems sound like they share the same acoustic space
    send_command("Filter: type=HighPass freq=40 rolloff=6dB")
    send_command("Filter: type=LowPass freq=16000 rolloff=6dB")

    # 3. Gentle compression for consistent dynamic range
    send_command(
        "Compressor: threshold=-18 ratio=3 attack=0.2 release=1.0 "
        "normalize=0 usePeak=0"
    )

    # 4. Export the processed file
    os.makedirs(os.path.dirname(output_wav), exist_ok=True)
    send_command(f'Export2: Filename="{output_wav}" NumChannels=2')
    send_command("Close:")
    time.sleep(0.5)
    print(f"  ✅ Saved: {output_wav}")


def batch_process(input_dir: str, output_dir: str) -> None:
    stems = glob.glob(os.path.join(input_dir, "*_raw.wav"))
    print(f"\n🎚️  Processing {len(stems)} stems...\n{'─'*50}")
    for stem_path in stems:
        base       = os.path.basename(stem_path).replace("_raw.wav", "_processed.wav")
        output_wav = os.path.join(output_dir, base)
        process_stem(stem_path, output_wav)
    print(f"\n✅ All processed stems saved to: {output_dir}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",  default="D:/GameProject/music/stems_raw/")
    parser.add_argument("--output", default="D:/GameProject/music/stems_processed/")
    args = parser.parse_args()
    batch_process(args.input, args.output)
```

#### The Split-and-Glue Loop Engineering Script

AI models generate audio with a natural beginning, middle, and end. This script turns any linear clip into a perfect seamless loop using the standard "swap halves" technique.

Save as `D:\GameProject\music\tools\make_seamless_loop.py`:

```python
"""
make_seamless_loop.py
Converts a linear AI audio file into a mathematically seamless loop
using the split-and-glue crossfade method.

Original AI Output:  [  Part A  ][  Part B  ]
After Processing:    [  Part B  ]╳[  Part A  ]
                                  ↑
                           (1-second crossfade)

Usage:
    python make_seamless_loop.py --input town_processed.wav --output town_loop.wav
"""

import numpy as np
import soundfile as sf
import argparse
import os


def make_seamless_loop(
    input_path: str,
    output_path: str,
    crossfade_seconds: float = 1.0
) -> None:
    audio, sample_rate = sf.read(input_path, dtype="float32")
    total_frames       = len(audio)
    mid_point          = total_frames // 2
    crossfade_frames   = int(crossfade_seconds * sample_rate)

    # Split into two halves
    part_a = audio[:mid_point]
    part_b = audio[mid_point:]

    # Swap: B comes first, A comes second
    swapped = np.concatenate([part_b, part_a], axis=0)

    # Build crossfade envelope around the new center seam
    fade_out = np.linspace(1.0, 0.0, crossfade_frames)
    fade_in  = np.linspace(0.0, 1.0, crossfade_frames)

    if audio.ndim == 2:  # Stereo
        fade_out = fade_out[:, np.newaxis]
        fade_in  = fade_in[:, np.newaxis]

    seam_start = mid_point - crossfade_frames // 2
    seam_end   = mid_point + crossfade_frames // 2

    # Apply the crossfade at the seam
    swapped[seam_start : seam_start + crossfade_frames] *= fade_out
    swapped[seam_end   : seam_end   + crossfade_frames] *= fade_in

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sf.write(output_path, swapped, sample_rate)
    print(f"✅ Seamless loop saved: {output_path}")
    print(f"   Duration: {len(swapped) / sample_rate:.1f}s | Crossfade: {crossfade_seconds}s")


def batch_loop_all(input_dir: str, output_dir: str, crossfade: float = 1.0) -> None:
    import glob
    stems = glob.glob(os.path.join(input_dir, "*_processed.wav"))
    print(f"\n🔄 Engineering seamless loops for {len(stems)} stems...")
    for stem in stems:
        out_name = os.path.basename(stem).replace("_processed.wav", "_loop.wav")
        make_seamless_loop(stem, os.path.join(output_dir, out_name), crossfade)
    print(f"\n✅ All loop files saved to: {output_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input",     default="D:/GameProject/music/stems_processed/")
    parser.add_argument("--output",    default="D:/GameProject/music/stems_final/")
    parser.add_argument("--crossfade", type=float, default=1.0)
    parser.add_argument("--single",    default=None, help="Process a single file instead of batch")
    args = parser.parse_args()

    if args.single:
        out = args.single.replace("_processed.wav", "_loop.wav")
        make_seamless_loop(args.single, os.path.join(args.output, os.path.basename(out)), args.crossfade)
    else:
        batch_loop_all(args.input, args.output, args.crossfade)
```

---

### 13.6 Layer 4 — Leitmotif Consistency Enforcement

Beyond the technical tools, these rules must be applied across every generation session.

#### The Locked Constraint Table

| Variable | How It Is Locked | Tool |
|---|---|---|
| **Melodic DNA** | All biomes use the same root MIDI before transformation | `transform_leitmotif.py` |
| **Scale relationships** | Each biome's scale is mathematically derived from the same root note (Middle C) | `pretty_midi` snap_to_scale() |
| **Sonic palette** | `CORE_SONIC_IDENTITY` string is identical in every prompt | `generate_music.py` |
| **Room acoustics** | Same IR convolution reverb applied to every stem | Audacity macro |
| **Loudness** | All stems normalized to −3 dB peak | Audacity macro |
| **Frequency range** | Shared high-pass (40 Hz) and low-pass (16 kHz) filters on all stems | Audacity macro |
| **Playback rate** | `MASTER_FPS`-equivalent for music: all biome themes share the same base BPM family | `generate_music.py` duration settings |
| **Loop length** | All loop durations are multiples of the base beat grid (32 or 64 seconds) | `make_seamless_loop.py` |

#### The Separate Melody Layer Strategy

For maximum leitmotif subtlety without re-generating full tracks, always export a second version of each stem with **only the background atmospheric layer** (no melody notes). In your AI prompt, explicitly request this:

```python
# Add to BIOME_PROMPTS as a companion variant:
"snow_ambient": (
    "frozen tundra ambient texture only, no melody, no lead instrument, "
    "sustained atmospheric string pad, slow evolving harmonic bed, "
    "60 BPM, background environment only"
),
```

In Godot, you then randomly alternate between the full stem (melody present) and the ambient-only stem, making the leitmotif feel like it surfaces and retreats organically.

---

### 13.7 Biome-by-Biome Generation Guide

#### Full Generation Command Sequence

```bash
# Step 1: Transform all MIDI biome variations
python music/tools/transform_leitmotif.py --input music/leitmotif_core.mid --biome all

# Step 2: Convert MIDI → WAV using FluidSynth (run for each biome)
for %b in (title town snow desert forest dungeon combat boss) do (
    fluidsynth -ni GeneralUser_GS.sf2 music/midi_variations/leitmotif_%b.mid -F music/midi_variations/wav/leitmotif_%b.wav -r 44100
)

# Step 3: Generate all orchestral stems via MusicGen-Melody
python music/tools/generate_music.py --biome all

# Step 4: Batch process all stems (EQ, normalize, reverb)
python music/tools/process_stems.py

# Step 5: Engineer seamless loops for all stems
python music/tools/make_seamless_loop.py
```

#### Biome Quick Reference

| Biome | Scale | Tempo | Key Instruments | Melody Treatment |
|---|---|---|---|---|
| **Title** | Major | 90 BPM | Full orchestra, brass, strings | Complete, definitive |
| **Town** | Major | 80 BPM | Solo guitar, light woodwinds | Complete, soft |
| **Snow** | Pentatonic Major | 60 BPM | Celesta, high strings | First 3 notes only, double length |
| **Desert** | Harmonic Minor | 110 BPM | Oud, hand drums, low cello | Full, bent to exotic scale |
| **Forest** | Dorian | 85 BPM | Oboe, french horn | Full, folk-like |
| **Dungeon** | Phrygian | 55 BPM | Low cellos, bassoon | First half of phrase, very slow |
| **Combat** | Harmonic Minor | 140 BPM | Staccato strings, brass, timpani | Full, double speed, punchy |
| **Boss** | Phrygian | 120 BPM | Massive low brass, choir | Full, lowest register |

---

### 13.8 Seamless Loop Engineering

Beyond the split-and-glue script, apply these rules to guarantee natural playback in-engine:

**BPM-to-Duration alignment formula:**

```
Loop Duration (seconds) = (Bars × Beats per Bar × 60) ÷ BPM

Example: 8 bars of 4/4 time at 90 BPM
= (8 × 4 × 60) ÷ 90 = 21.3 seconds  ← NOT clean

Try 16 bars:
= (16 × 4 × 60) ÷ 90 = 42.7 seconds ← still not clean

Use 12 bars at 90 BPM:
= (12 × 4 × 60) ÷ 90 = 32 seconds   ← CLEAN LOOP ✅
```

When setting duration in `generate_music.py`, always verify the duration results in a whole number using this formula before generating. The `BIOME_DURATION` dictionary in the script is already pre-calculated for common BPM values.

**The Layered Loop Strategy:**

Rather than looping a single 3-minute track, export two files per biome:

```
snow_loop.wav          ← 64s atmospheric pad (loops endlessly)
snow_melody_layer.wav  ← 32s leitmotif fragment (triggered randomly)
```

In Godot, the atmospheric pad plays permanently while the melody layer surfaces every 45–90 seconds. The player experiences a living, breathing environment rather than a repetitive loop.

---

### 13.9 Godot 4 Adaptive Music Integration

#### Music Manager (Autoload)

Create `D:\GameProject\src\systems\MusicManager.gd` and register as an **Autoload** in Project Settings:

```gdscript
# MusicManager.gd — Adaptive leitmotif-aware music system
# Handles: biome crossfading, random melody surfacing, smooth transitions
extends Node

const FADE_DURATION: float  = 2.5   # Seconds to crossfade between biomes
const MELODY_MIN_WAIT: float = 45.0  # Minimum seconds between melody appearances
const MELODY_MAX_WAIT: float = 90.0  # Maximum seconds between melody appearances

# ─────────────────────────────────────────────────────────
# Preload all music assets
# ─────────────────────────────────────────────────────────
var biome_pads: Dictionary = {
    "title":   preload("res://audio/music/title_loop.wav"),
    "town":    preload("res://audio/music/town_loop.wav"),
    "snow":    preload("res://audio/music/snow_loop.wav"),
    "desert":  preload("res://audio/music/desert_loop.wav"),
    "forest":  preload("res://audio/music/forest_loop.wav"),
    "dungeon": preload("res://audio/music/dungeon_loop.wav"),
    "combat":  preload("res://audio/music/combat_loop.wav"),
    "boss":    preload("res://audio/music/boss_loop.wav"),
}

var biome_melodies: Dictionary = {
    "title":   preload("res://audio/music/title_melody.wav"),
    "town":    preload("res://audio/music/town_melody.wav"),
    "snow":    preload("res://audio/music/snow_melody.wav"),
    "desert":  preload("res://audio/music/desert_melody.wav"),
    "forest":  preload("res://audio/music/forest_melody.wav"),
    "dungeon": preload("res://audio/music/dungeon_melody.wav"),
    "combat":  preload("res://audio/music/combat_melody.wav"),
    "boss":    preload("res://audio/music/boss_melody.wav"),
}

# ─────────────────────────────────────────────────────────
# Runtime state
# ─────────────────────────────────────────────────────────
var _current_biome:  String = ""
var _pad_player_a:   AudioStreamPlayer
var _pad_player_b:   AudioStreamPlayer
var _melody_player:  AudioStreamPlayer
var _active_player:  AudioStreamPlayer  # Which pad player is currently audible
var _melody_timer:   Timer


func _ready() -> void:
    _pad_player_a  = _make_player("MusicPad_A", "Music")
    _pad_player_b  = _make_player("MusicPad_B", "Music")
    _melody_player = _make_player("MusicMelody", "Melody")

    _melody_timer = Timer.new()
    add_child(_melody_timer)
    _melody_timer.timeout.connect(_surface_leitmotif)

    _active_player = _pad_player_a


func _make_player(node_name: String, bus_name: String) -> AudioStreamPlayer:
    var player := AudioStreamPlayer.new()
    player.name   = node_name
    player.bus    = bus_name
    player.volume_db = -80.0  # Start silent
    add_child(player)
    return player


# ─────────────────────────────────────────────────────────
# Public API — call from any scene or zone trigger
# ─────────────────────────────────────────────────────────
func transition_to_biome(biome_name: String) -> void:
    if biome_name == _current_biome:
        return
    if not biome_pads.has(biome_name):
        push_warning("MusicManager: Unknown biome '%s'" % biome_name)
        return

    _current_biome = biome_name
    print("🎵 Music transition → %s" % biome_name)

    # Assign new stream to the inactive player, then crossfade
    var incoming := _pad_player_b if _active_player == _pad_player_a else _pad_player_a
    incoming.stream    = biome_pads[biome_name]
    incoming.volume_db = -80.0
    incoming.play()

    # Crossfade: fade out active, fade in incoming
    var tween := create_tween().set_parallel(true)
    tween.tween_property(_active_player, "volume_db", -80.0, FADE_DURATION)
    tween.tween_property(incoming,       "volume_db", 0.0,   FADE_DURATION)
    await tween.finished

    _active_player.stop()
    _active_player = incoming

    # Schedule the next random melody appearance
    _schedule_melody()


func stop_music(fade_time: float = 2.0) -> void:
    var tween := create_tween()
    tween.tween_property(_active_player, "volume_db", -80.0, fade_time)
    await tween.finished
    _active_player.stop()
    _melody_timer.stop()
    _current_biome = ""


# ─────────────────────────────────────────────────────────
# Leitmotif surfacing — random, organic, non-repetitive
# ─────────────────────────────────────────────────────────
func _schedule_melody() -> void:
    _melody_timer.stop()
    if not biome_melodies.has(_current_biome):
        return
    var wait_time := randf_range(MELODY_MIN_WAIT, MELODY_MAX_WAIT)
    _melody_timer.start(wait_time)


func _surface_leitmotif() -> void:
    if _current_biome == "" or not biome_melodies.has(_current_biome):
        return

    _melody_player.stream    = biome_melodies[_current_biome]
    _melody_player.volume_db = 0.0
    _melody_player.play()
    print("🎶 Leitmotif surfaced for: %s" % _current_biome)

    # Fade melody out after it plays, then schedule the next appearance
    await _melody_player.finished
    _schedule_melody()
```

#### Zone Trigger (Attach to Area2D nodes in your map scenes)

```gdscript
# BiomeMusicTrigger.gd — Attach to an Area2D covering each biome zone
extends Area2D

@export var biome_name: String = "town"

func _ready() -> void:
    body_entered.connect(_on_body_entered)


func _on_body_entered(body: Node) -> void:
    if body.is_in_group("player"):
        MusicManager.transition_to_biome(biome_name)
```

#### Godot Audio Bus Setup

In **Project → Audio**, create these buses:

| Bus Name | Effect | Setting |
|---|---|---|
| **Music** | None | Volume: 0 dB |
| **Melody** | None | Volume: −3 dB (slightly quieter so melody feels subtle) |
| **UI** | None | Volume: 0 dB |
| **GameWorld** | Bitcrusher (8-bit depth) | Volume: 0 dB |

---

### 13.10 Music Generation Checklist

#### Before Every Generation Session

- [ ] `leitmotif_core.mid` and `leitmotif_core.wav` are saved in `music/`
- [ ] FluidSynth and the GS soundfont are accessible from your terminal
- [ ] AudioCraft is installed and the `musicgen-melody` weights are cached
- [ ] Audacity is open with `mod-script-pipe` enabled
- [ ] `CORE_SONIC_IDENTITY` in `generate_music.py` is unchanged from the last session

#### Per-Biome Quality Check

Before importing any stem into Godot, verify:

- [ ] The leitmotif is audibly present (even if subtle)
- [ ] The loop point is inaudible when the track repeats back-to-back
- [ ] The stem's loudness matches other biome stems (peak around −3 dB)
- [ ] The acoustic space sounds like the same "room" as other stems
- [ ] The instrumentation does not introduce any sounds outside your `CORE_SONIC_IDENTITY`

#### Music Consistency Layer Summary

| Layer | Tool | What It Locks |
|---|---|---|
| **1. Melodic DNA** | `transform_leitmotif.py` | All biomes share the same root MIDI notes |
| **2. Scale Logic** | `pretty_midi` snap_to_scale() | Biome scales are mathematically derived from the same root |
| **3. Sonic Identity** | `CORE_SONIC_IDENTITY` prompt string | Instrumentation palette is identical across all AI calls |
| **4. Room Acoustics** | Audacity IR convolution macro | All stems sound recorded in the same physical space |
| **5. Loudness** | Audacity normalization (−3 dB) | No stem is louder or quieter than another |
| **6. Frequency Range** | Audacity EQ macro (40 Hz–16 kHz) | All stems share the same tonal bandwidth |
| **7. Loop Structure** | `make_seamless_loop.py` | Every loop is mathematically gapless |
| **8. In-Game Surfacing** | `MusicManager.gd` + random timer | Leitmotif appears organically, never mechanically |

---

## 14. ComfyUI Workflow Scripting (No GUI)

Building workflows through the ComfyUI browser interface is useful for prototyping, but it is slow, unrepeatable, and impossible to version-control. Every workflow you use in production should exist as a Python class that can be constructed, modified, and submitted to the API without ever opening a browser tab.

This section explains how to understand the ComfyUI API format and replace the GUI entirely with code.

---

### 14.1 How the ComfyUI API Works

When you click **Queue Prompt** in the ComfyUI browser, it sends a single HTTP POST to `http://127.0.0.1:8188/prompt`. The body is a JSON object called a **prompt graph** — a flat dictionary of numbered nodes, each representing one node in the visual workflow.

Every node has the same shape:

```json
{
  "NODE_ID": {
    "class_type": "NodeClassName",
    "inputs": {
      "some_input_value": 512,
      "linked_input":     ["SOURCE_NODE_ID", OUTPUT_SLOT_INDEX]
    }
  }
}
```

The two input types are:

- **Literal values** — numbers, strings, booleans passed directly: `"width": 512`
- **Node links** — a two-element array `["node_id", slot]` wiring one node's output into another's input: `["4", 0]` means "take output slot 0 from node 4"

This means an entire ComfyUI visual workflow is just a Python dictionary. Every connection you draw with your mouse in the GUI becomes one of these two-element arrays.

#### Finding Class Names

To see the exact `class_type` string for any node, hover over it in the ComfyUI GUI and read the title, or query the API directly:

```bash
# Returns a JSON object listing every installed node and its input schema
curl http://127.0.0.1:8188/object_info > comfyui_node_reference.json
```

Save this output — it is your complete reference for every node name and parameter available in your ComfyUI installation.

---

### 14.2 Reading and Exporting Workflows as JSON

The fastest way to understand an existing workflow is to export it from the GUI in **API format**, then read the resulting JSON.

**In ComfyUI browser:**
1. Build or open your workflow
2. Click the gear icon → enable **Dev Mode Options**
3. Click **Save (API Format)** — this saves the raw prompt graph, not the visual layout
4. Open the file in any text editor

The resulting file is exactly what Python sends to the `/prompt` endpoint. You can load and submit it directly:

```python
import json, urllib.request

def submit_workflow_file(json_path: str, server: str = "http://127.0.0.1:8188") -> str:
    with open(json_path) as f:
        workflow = json.load(f)
    payload  = json.dumps({"prompt": workflow}).encode()
    req      = urllib.request.Request(f"{server}/prompt", data=payload)
    response = urllib.request.urlopen(req)
    return json.loads(response.read())["prompt_id"]

prompt_id = submit_workflow_file("workflows/character_sprite.json")
print(f"Queued: {prompt_id}")
```

This bridges GUI-built workflows and code-controlled submission. Export once, then modify the dictionary in Python rather than clicking nodes.

---

### 14.3 The WorkflowBuilder Class

Rather than maintaining separate JSON files that are hard to modify programmatically, use a `WorkflowBuilder` class that constructs node graphs as Python dictionaries. This makes workflows composable, readable, and parameterized.

Save as `D:\GameProject\tools\workflow_builder.py`:

```python
"""
workflow_builder.py
Constructs ComfyUI workflow graphs as Python dictionaries without the GUI.
Each method adds one node to the graph and returns its node ID for wiring.

Usage:
    from workflow_builder import WorkflowBuilder
    wb      = WorkflowBuilder()
    model   = wb.load_checkpoint("sd_v1-5.safetensors")
    lora    = wb.load_lora(model, "my_game_style.safetensors", strength=0.85)
    pos     = wb.clip_encode(lora, "my pixel art sprite")
    neg     = wb.clip_encode(lora, "blurry, photorealistic")
    latent  = wb.empty_latent(512, 512)
    sampled = wb.ksampler(model, pos, neg, latent)
    decoded = wb.vae_decode(sampled, model)
    wb.save_image(decoded, "output_prefix")
    paths   = wb.run("res/art/sprites/")
"""

import json, uuid, random, os
import urllib.request, urllib.parse
import websocket


class WorkflowBuilder:
    def __init__(self, server_url: str = "http://127.0.0.1:8188"):
        self.server    = server_url
        self.client_id = str(uuid.uuid4())
        self.graph: dict = {}
        self._counter    = 1

    # ── Internal helpers ──────────────────────────────────
    def _node(self, class_type: str, inputs: dict) -> str:
        node_id = str(self._counter)
        self._counter += 1
        self.graph[node_id] = {"class_type": class_type, "inputs": inputs}
        return node_id

    def _link(self, node_id: str, slot: int = 0) -> list:
        return [node_id, slot]

    def reset(self) -> None:
        self.graph = {}
        self._counter = 1

    # ── Model loaders ─────────────────────────────────────
    def load_checkpoint(self, ckpt_name: str) -> str:
        """Outputs: [0]=MODEL [1]=CLIP [2]=VAE"""
        return self._node("CheckpointLoaderSimple", {"ckpt_name": ckpt_name})

    def load_lora(self, checkpoint_node: str, lora_name: str,
                  strength_model: float = 0.85, strength_clip: float = 0.85) -> str:
        """Outputs: [0]=MODEL [1]=CLIP"""
        return self._node("LoraLoader", {
            "model":          self._link(checkpoint_node, 0),
            "clip":           self._link(checkpoint_node, 1),
            "lora_name":      lora_name,
            "strength_model": strength_model,
            "strength_clip":  strength_clip,
        })

    def load_vae(self, vae_name: str) -> str:
        """Output: [0]=VAE"""
        return self._node("VAELoader", {"vae_name": vae_name})

    # ── Text conditioning ─────────────────────────────────
    def clip_encode(self, model_or_lora_node: str, text: str, clip_slot: int = 1) -> str:
        """Output: [0]=CONDITIONING"""
        return self._node("CLIPTextEncode", {
            "clip": self._link(model_or_lora_node, clip_slot),
            "text": text,
        })

    # ── Latent space ──────────────────────────────────────
    def empty_latent(self, width: int = 512, height: int = 512, batch: int = 1) -> str:
        """Output: [0]=LATENT"""
        return self._node("EmptyLatentImage", {
            "width": width, "height": height, "batch_size": batch,
        })

    def encode_image_to_latent(self, image_node: str, vae_node: str, vae_slot: int = 2) -> str:
        """Encode an image into latent space for img2img. Output: [0]=LATENT"""
        return self._node("VAEEncode", {
            "pixels": self._link(image_node, 0),
            "vae":    self._link(vae_node, vae_slot),
        })

    # ── Sampling ──────────────────────────────────────────
    def ksampler(self, model_node: str, positive_node: str, negative_node: str,
                 latent_node: str, seed: int = -1, steps: int = 20,
                 cfg: float = 7.0, sampler_name: str = "euler_ancestral",
                 scheduler: str = "karras", denoise: float = 1.0) -> str:
        """Output: [0]=LATENT"""
        return self._node("KSampler", {
            "model":        self._link(model_node, 0),
            "positive":     self._link(positive_node, 0),
            "negative":     self._link(negative_node, 0),
            "latent_image": self._link(latent_node, 0),
            "seed":         seed if seed >= 0 else random.randint(0, 2**32 - 1),
            "steps":        steps, "cfg": cfg,
            "sampler_name": sampler_name, "scheduler": scheduler, "denoise": denoise,
        })

    # ── Decoding & output ─────────────────────────────────
    def vae_decode(self, latent_node: str, checkpoint_or_vae_node: str, vae_slot: int = 2) -> str:
        """Output: [0]=IMAGE"""
        return self._node("VAEDecode", {
            "samples": self._link(latent_node, 0),
            "vae":     self._link(checkpoint_or_vae_node, vae_slot),
        })

    def save_image(self, image_node: str, filename_prefix: str = "output") -> str:
        return self._node("SaveImage", {
            "images":          self._link(image_node, 0),
            "filename_prefix": filename_prefix,
        })

    # ── Image loading ─────────────────────────────────────
    def load_image(self, image_filename: str) -> str:
        """Load image already uploaded to ComfyUI input folder. Output: [0]=IMAGE [1]=MASK"""
        return self._node("LoadImage", {"image": image_filename, "upload": "image"})

    # ── ControlNet ────────────────────────────────────────
    def load_controlnet(self, controlnet_name: str) -> str:
        """Output: [0]=CONTROL_NET"""
        return self._node("ControlNetLoader", {"control_net_name": controlnet_name})

    def apply_controlnet(self, positive_node: str, negative_node: str,
                         controlnet_node: str, image_node: str,
                         strength: float = 0.85, start_percent: float = 0.0,
                         end_percent: float = 0.8) -> tuple:
        """Returns (positive_node_id, negative_node_id) — both are the same CN node."""
        cn = self._node("ControlNetApplyAdvanced", {
            "positive":      self._link(positive_node, 0),
            "negative":      self._link(negative_node, 0),
            "control_net":   self._link(controlnet_node, 0),
            "image":         self._link(image_node, 0),
            "strength":      strength,
            "start_percent": start_percent,
            "end_percent":   end_percent,
        })
        return cn, cn

    def canny_preprocessor(self, image_node: str,
                           low_threshold: int = 100, high_threshold: int = 200) -> str:
        """Output: [0]=IMAGE"""
        return self._node("CannyEdgePreprocessor", {
            "image":          self._link(image_node, 0),
            "low_threshold":  low_threshold,
            "high_threshold": high_threshold,
            "resolution":     512,
        })

    def openpose_preprocessor(self, image_node: str) -> str:
        """Output: [0]=IMAGE"""
        return self._node("OpenposePreprocessor", {
            "image":       self._link(image_node, 0),
            "detect_hand": "enable",
            "detect_body": "enable",
            "detect_face": "disable",
            "resolution":  512,
        })

    # ── IP-Adapter ────────────────────────────────────────
    def load_ipadapter(self, ipadapter_name: str) -> str:
        """Output: [0]=IPADAPTER"""
        return self._node("IPAdapterModelLoader", {"ipadapter_file": ipadapter_name})

    def load_clip_vision(self, clip_vision_name: str) -> str:
        """Output: [0]=CLIP_VISION"""
        return self._node("CLIPVisionLoader", {"clip_name": clip_vision_name})

    def apply_ipadapter(self, model_node: str, ipadapter_node: str,
                        clip_vision_node: str, image_node: str,
                        weight: float = 0.75, noise: float = 0.1,
                        start_at: float = 0.0, end_at: float = 1.0) -> str:
        """Output: [0]=MODEL"""
        return self._node("IPAdapterAdvanced", {
            "model":       self._link(model_node, 0),
            "ipadapter":   self._link(ipadapter_node, 0),
            "clip_vision": self._link(clip_vision_node, 0),
            "image":       self._link(image_node, 0),
            "weight":      weight, "noise": noise,
            "start_at":    start_at, "end_at": end_at,
            "weight_type": "original",
        })

    # ── Pixel art post-processing ─────────────────────────
    def palette_match(self, image_node: str, palette_image_node: str) -> str:
        """Output: [0]=IMAGE"""
        return self._node("PaletteMatch", {
            "images":  self._link(image_node, 0),
            "palette": self._link(palette_image_node, 0),
            "dither":  "false",
        })

    def pixel_art_downscale(self, image_node: str, target_size: int = 32) -> str:
        """Downscale using Nearest Neighbor. Output: [0]=IMAGE"""
        return self._node("ImageScale", {
            "image":          self._link(image_node, 0),
            "width":          target_size,
            "height":         target_size,
            "upscale_method": "nearest-exact",
            "crop":           "disabled",
        })

    def image_tiling(self, image_node: str) -> str:
        """Apply seamless tiling for terrain textures. Output: [0]=IMAGE"""
        return self._node("MakeImageTile", {"image": self._link(image_node, 0)})

    # ── API submission ────────────────────────────────────
    def get_graph(self) -> dict:
        return self.graph

    def save_to_file(self, path: str) -> None:
        """Save workflow as JSON — importable back into the ComfyUI GUI."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.graph, f, indent=2)
        print(f"Workflow saved: {path}")

    def submit(self) -> str:
        """Submit the current graph to ComfyUI and return the prompt_id."""
        payload  = json.dumps({"prompt": self.graph, "client_id": self.client_id}).encode()
        req      = urllib.request.Request(f"{self.server}/prompt", data=payload)
        response = urllib.request.urlopen(req)
        return json.loads(response.read())["prompt_id"]

    def wait_for_completion(self, prompt_id: str) -> None:
        """Block until the queued prompt finishes generating."""
        ws = websocket.WebSocket()
        ws.connect(f"ws://{self.server.replace('http://', '')}/ws?clientId={self.client_id}")
        while True:
            msg = json.loads(ws.recv())
            if (msg.get("type") == "executing"
                    and msg["data"].get("prompt_id") == prompt_id
                    and msg["data"].get("node") is None):
                break
        ws.close()

    def get_output_images(self, prompt_id: str) -> list:
        req     = urllib.request.urlopen(f"{self.server}/history/{prompt_id}")
        history = json.loads(req.read())
        images  = []
        for node_output in history[prompt_id]["outputs"].values():
            if "images" in node_output:
                images.extend(node_output["images"])
        return images

    def download_outputs(self, prompt_id: str, output_dir: str) -> list:
        images = self.get_output_images(prompt_id)
        os.makedirs(output_dir, exist_ok=True)
        saved  = []
        for img in images:
            params = urllib.parse.urlencode({
                "filename": img["filename"],
                "subfolder": img.get("subfolder", ""),
                "type":     img.get("type", "output"),
            })
            data     = urllib.request.urlopen(f"{self.server}/view?{params}").read()
            out_path = os.path.join(output_dir, img["filename"])
            with open(out_path, "wb") as f:
                f.write(data)
            saved.append(out_path)
            print(f"  Downloaded: {out_path}")
        return saved

    def run(self, output_dir: str) -> list:
        """Submit → wait → download. Full single-call generation."""
        pid = self.submit()
        print(f"Queued: {pid[:8]}...")
        self.wait_for_completion(pid)
        return self.download_outputs(pid, output_dir)
```

---

### 14.4 Pre-Built Workflow Scripts by Asset Type

Each function below constructs and submits a complete workflow using `WorkflowBuilder`. These replace standalone JSON workflow files entirely.

Save as `D:\GameProject\tools\workflows.py`:

```python
"""
workflows.py
Parameterized workflow constructors for each asset type.
Import and call these functions directly from automation scripts.
"""

import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workflow_builder import WorkflowBuilder, upload_image

with open("style_config.json") as f:
    CFG = json.load(f)

BASE_MODEL  = CFG["base_model"]
LORA_NAME   = CFG["lora_name"]
LORA_STR    = CFG["lora_strength"]
PIXEL_SIZE  = CFG["pixel_grid_size"]
GEN_RES     = CFG["generation_resolution"]
POS_ANCHORS = ", ".join(CFG["positive_anchors"])
NEG_ANCHORS = ", ".join(CFG["negative_anchors"])

IPADAPTER_MODEL = "ip-adapter-plus_sd15.safetensors"
CLIP_VISION     = "clip_vision_g.safetensors"
CN_CANNY        = "control_v11p_sd15_canny.pth"
CN_OPENPOSE     = "control_v11p_sd15_openpose.pth"


def _base(positive_text: str, negative_text: str = None):
    """Shared foundation: checkpoint → LoRA → conditioning."""
    wb   = WorkflowBuilder()
    ckpt = wb.load_checkpoint(BASE_MODEL)
    lora = wb.load_lora(ckpt, LORA_NAME, LORA_STR, LORA_STR)
    pos  = wb.clip_encode(lora, f"{POS_ANCHORS}, {positive_text}")
    neg  = wb.clip_encode(lora, negative_text or NEG_ANCHORS)
    return wb, lora, pos, neg


def generate_concept_art(positive_prompt: str, output_dir: str,
                         reference_image: str = None) -> list:
    wb, lora, pos, neg = _base(positive_prompt)
    model_node = lora
    if reference_image:
        ref = wb.load_image(upload_image(reference_image))
        ipa = wb.load_ipadapter(IPADAPTER_MODEL)
        cv  = wb.load_clip_vision(CLIP_VISION)
        model_node = wb.apply_ipadapter(lora, ipa, cv, ref, weight=0.7)
    latent  = wb.empty_latent(768, 768)
    sampled = wb.ksampler(model_node, pos, neg, latent, steps=30, cfg=7.5)
    decoded = wb.vae_decode(sampled, lora)
    palette = wb.load_image(upload_image(CFG["master_palette_path"]))
    matched = wb.palette_match(decoded, palette)
    wb.save_image(matched, "concept")
    return wb.run(output_dir)


def generate_character_sprite(positive_prompt: str, output_dir: str,
                               concept_ref: str = None, skeleton_image: str = None) -> list:
    wb, lora, pos, neg = _base(positive_prompt)
    model_node = lora
    if concept_ref:
        ref        = wb.load_image(upload_image(concept_ref))
        ipa        = wb.load_ipadapter(IPADAPTER_MODEL)
        cv         = wb.load_clip_vision(CLIP_VISION)
        model_node = wb.apply_ipadapter(model_node, ipa, cv, ref, weight=0.75)
    if skeleton_image:
        skel     = wb.load_image(upload_image(skeleton_image))
        pose_map = wb.openpose_preprocessor(skel)
        cn       = wb.load_controlnet(CN_OPENPOSE)
        pos, neg = wb.apply_controlnet(pos, neg, cn, pose_map, strength=0.85)
    latent  = wb.empty_latent(GEN_RES, GEN_RES)
    sampled = wb.ksampler(model_node, pos, neg, latent, steps=25, cfg=7.0)
    decoded = wb.vae_decode(sampled, lora)
    palette = wb.load_image(upload_image(CFG["master_palette_path"]))
    matched = wb.palette_match(decoded, palette)
    ds      = wb.pixel_art_downscale(matched, PIXEL_SIZE)
    wb.save_image(ds, "sprite")
    return wb.run(output_dir)


def generate_terrain_tile(positive_prompt: str, output_dir: str,
                          concept_ref: str = None) -> list:
    wb, lora, pos, neg = _base(positive_prompt)
    model_node = lora
    if concept_ref:
        ref      = wb.load_image(upload_image(concept_ref))
        canny    = wb.canny_preprocessor(ref)
        cn       = wb.load_controlnet(CN_CANNY)
        pos, neg = wb.apply_controlnet(pos, neg, cn, canny, strength=0.65)
        ipa      = wb.load_ipadapter(IPADAPTER_MODEL)
        cv       = wb.load_clip_vision(CLIP_VISION)
        model_node = wb.apply_ipadapter(model_node, ipa, cv, ref, weight=0.6)
    latent  = wb.empty_latent(GEN_RES, GEN_RES)
    sampled = wb.ksampler(model_node, pos, neg, latent, steps=25, cfg=7.0)
    decoded = wb.vae_decode(sampled, lora)
    tiled   = wb.image_tiling(decoded)
    palette = wb.load_image(upload_image(CFG["master_palette_path"]))
    matched = wb.palette_match(tiled, palette)
    ds      = wb.pixel_art_downscale(matched, PIXEL_SIZE)
    wb.save_image(ds, "terrain")
    return wb.run(output_dir)


def generate_ui_element(positive_prompt: str, output_dir: str,
                        wireframe_image: str = None) -> list:
    wb, lora, pos, neg = _base(positive_prompt)
    if wireframe_image:
        wf       = wb.load_image(upload_image(wireframe_image))
        canny    = wb.canny_preprocessor(wf, 50, 150)
        cn       = wb.load_controlnet(CN_CANNY)
        pos, neg = wb.apply_controlnet(pos, neg, cn, canny, strength=0.9)
    latent  = wb.empty_latent(GEN_RES, GEN_RES)
    sampled = wb.ksampler(lora, pos, neg, latent, steps=25, cfg=7.5)
    decoded = wb.vae_decode(sampled, lora)
    palette = wb.load_image(upload_image(CFG["master_palette_path"]))
    matched = wb.palette_match(decoded, palette)
    ds      = wb.pixel_art_downscale(matched, PIXEL_SIZE)
    wb.save_image(ds, "ui")
    return wb.run(output_dir)


def generate_normal_map(albedo_image: str, output_dir: str) -> list:
    wb  = WorkflowBuilder()
    alb = wb.load_image(upload_image(albedo_image))
    depth = wb._node("MiDaS-DepthMapPreprocessor", {
        "image":        wb._link(alb, 0),
        "a":            6.283185307179586,
        "bg_threshold": 0.1,
        "resolution":   GEN_RES,
    })
    ds = wb.pixel_art_downscale(depth, PIXEL_SIZE)
    wb.save_image(ds, "normal_map")
    return wb.run(output_dir)
```

---

### 14.5 Uploading Reference Images Programmatically

Before a local image can be used inside a workflow via `LoadImage`, it must be uploaded to ComfyUI's input directory. Add this function to `workflow_builder.py`:

```python
def upload_image(local_path: str, server_url: str = "http://127.0.0.1:8188",
                 subfolder: str = "", overwrite: bool = True) -> str:
    """
    Upload a local image to ComfyUI's input folder via multipart POST.
    Returns the filename ComfyUI assigned — pass this to wb.load_image().
    """
    import urllib.request, json, os

    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Not found: {local_path}")

    filename = os.path.basename(local_path)
    with open(local_path, "rb") as f:
        file_data = f.read()

    boundary = "----PythonUploadBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + file_data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="subfolder"\r\n\r\n{subfolder}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="overwrite"\r\n\r\n'
        f"{'true' if overwrite else 'false'}\r\n"
        f"--{boundary}--\r\n"
    ).encode()

    req = urllib.request.Request(
        f"{server_url}/upload/image", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    result = json.loads(urllib.request.urlopen(req).read())
    uploaded_name = result.get("name", filename)
    print(f"  Uploaded '{filename}' → ComfyUI: '{uploaded_name}'")
    return uploaded_name
```

