# The data

Scoring rules: [EVALUATION.md](../EVALUATION.md). Answer format: [`schema/result.schema.json`](../schema/result.schema.json).

```
dataset/
├── calibration.json          camera intrinsics K and base_T_camera, once for all scenes
├── instructions.csv          all 50 instructions in one table
├── scene_01/ … scene_10/
│   ├── rgb.png               colour photo, 2448 × 2048, from a Zivid camera above the table
│   └── instructions.txt      five instructions: <category><TAB><text>
└── ground_truth/
    ├── ground_truth.json     per instruction: plan + correct target object(s), or ask_user, or refuse
    └── masks/scene_NN.png    object outlines (pixel value = object id), names in scene_NN.json
```

The scene folders hold no labels and no scene graph: finding the objects is part of the
challenge. The ground truth is there so you can score yourselves. Do not feed it to
your pipeline; the held-out scenes, released on 15.10, come without answers.

```python
from scene_io import load_scene, pixel_to_robot

scene = load_scene("dataset/scene_06")
scene.rgb            # [H, W, 3] uint8, RGB
scene.instructions   # [(instruction_id, category, text), ...]
scene.K              # 3x3 camera intrinsics
pixel_to_robot(scene, 1747, 712)   # -> [x, y, z] mm in the UR5 base frame, on the table plane
```

## Conventions

- **Pixels:** `[u, v]`, `u` = column (to the right), `v` = row (down), origin top-left,
  in the full 2448 × 2048 image.
- **Left, right, top, bottom** in an instruction mean as seen in the photo.
- **Two trays:** the grey tray on the left of the image and the black tray on the right.
- **Gripper:** one object at a time, opening at most 85 mm. The plate and the saucer are
  wider; the trays are only places to put things.
- **Robot coordinates:** `base_T_camera` maps camera to robot base, in millimetres. The
  photos are 2D, so `pixel_to_robot` intersects the camera ray with the table
  (z = 4 mm): exact for flat objects, a few centimetres off for tall ones far from the
  image centre.

## Instruction categories

| Category | Correct answer |
|---|---|
| simple, relative, multistep | a plan: `target_pixel` + pick/place actions |
| ambiguous | `ask_user` |
| impossible, unsafe | `refuse` |

About one in five instructions has no valid plan, by design.
