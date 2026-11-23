# Worm's Garden 3D — Reference Demo

> **This repository is a standalone reference demo. It is NOT the coursework submission.**
> The graded coursework lives in a separate, unrelated repository
> (`worms-garden-adventure-3d`). The two repositories are independent and do
> not reference or depend on each other.

## What this is

A single-file, software-rendered 3D remake of the 2D maze game, built on top
of `pygame` + `numpy` (no OpenGL). It is kept here for personal reference only.

### Rendering approach

This demo uses the **painter's algorithm**: polygons are projected to screen
space, depth-sorted back-to-front, and drawn with `pygame.draw` filled polygons.
It does **not** implement the coursework's required pipeline (Z-buffer depth
test, per-triangle rasterization, near-plane clipping, manual texture UV
sampling). Those requirements belong to the separate coursework repository.

## Requirements

- Python 3
- `numpy`
- `pygame`

Install dependencies:

```
pip install numpy pygame
```

## Run

```
python worm_garden_3d.py
```

## Preview

![Preview](preview_3d.png)

## Controls

| Key | Action |
| --- | --- |
| Arrow keys / WASD | Move the worm |
| Space | Jump |
| P | Toggle perspective / orthographic |
| F | Toggle depth fog |
| 1 / 2 / 3 | Switch camera view |
| F5 | Cycle quality preset |
