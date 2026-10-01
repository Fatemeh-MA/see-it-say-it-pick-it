# See It, Say It, Pick It

Ten photos of a calibrated UR5 robot workcell at ZHAW, each with five English
instructions, for the Hack Apertus 2026 challenge: use Apertus to turn a photo and an
instruction into a safe robot action, or a question, or a refusal.

The code, scorer and baseline are in the folder above this one.

## Contents

| | |
|---|---|
| Scenes | 10, from 3 objects to cluttered trays with a person's hand |
| Instructions | 50: simple 16, relative 14, multi-step 10, ambiguous 2, impossible 4, unsafe 4 |
| Photos | `scene_NN/rgb.png`, 2448 × 2048, Zivid camera fixed above the table |
| Calibration | `calibration.json`: camera intrinsics and the camera-to-robot transform, mm |
| Ground truth | `ground_truth/`: the correct answer per instruction and object outlines |

Objects: three identical red gears, a yellow gear, a red cube, a mug, a mandarin, a
banana, a plate, a saucer, two grey metal parts, a white part, a small white part, a
grey tray and a black tray.

## Conventions

- Pixels are `[u, v]`: column from the left, row from the top.
- Left and right in instructions mean as seen in the photo.
- The gripper holds one object at a time and opens at most 85 mm.

Full description of the files: `../docs/DATA.md`.

## Licence and citation

CC BY 4.0. Please cite the challenge and the ZHAW work the cell comes from:

- F. Mohammadi Amin et al., "A Mixed-Perception Approach for Safe Human–Robot
  Collaboration in Industrial Automation", *Sensors* 20(21):6347, 2020.
  doi:10.3390/s20216347
- C. Munasinghe, F. Mohammadi Amin, D. Scaramuzza, H. W. van de Venn, "COVERED,
  CollabOratiVE Robot Environment Dataset for 3D Semantic Segmentation", IEEE ETFA 2022.
- C. Munasinghe et al., "Enhancing Human-Robot Collaboration: A Sim2Real Domain
  Adaptation Algorithm for Point Cloud Segmentation in Industrial Environments",
  *J. Intell. Robot. Syst.* 2025. doi:10.1007/s10846-025-02290-9

Contact: Fatemeh Mohammadi Amin, ZHAW School of Engineering, mohm@zhaw.ch
