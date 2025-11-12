# squawk-farm

# Directory Structure

```
squawk-farm/
├── main.py                      # Kivy entrypoint
│
├── squawkfarm/                  # your app code
│   ├── __init__.py
│   ├── app.py                   # builds Kivy App + ScreenManager (can use imslib)
│   │
│   ├── screens/                 # all UI screens (Kivy Screen subclasses)
│   │   ├── __init__.py
│   │   ├── garden_screen.py     # main "garden" view
│   │   ├── record_screen.py     # record a new animal sound
│   │   └── loop_editor_screen.py# edit loops / beat grid
│   │
│   ├── ui/                      # reusable UI widgets
│   │   ├── __init__.py
│   │   └── loop_grid.py         # visual grid for tempo/measure display
│   │
│   ├── services/                # app logic (no UI here)
│   │   ├── __init__.py
│   │   ├── feature_extract.py   # .wav → animal features
│   │   ├── animal_gen.py        # features → animal config (can start from assets)
│   │   ├── loop_engine.py       # global tempo/meter + per-animal loops
│   │   ├── animation_sync.py    # beat → animation triggers
│   │   └── save_load.py         # save/load full garden compositions
│   │
│   ├── models/                  # data structures
│   │   ├── __init__.py
│   │   ├── animal.py            # Animal, AnimalAttributes
│   │   ├── loop.py              # GlobalLoopSettings, AnimalLoop
│   │   └── project.py           # Project
│   │
│   └── utils/                   # small helpers
│       ├── __init__.py
│       ├── audio_utils.py       # load/save wav, paths, normalization
│       ├── path_utils.py        # construct paths to project assets and data
│       └── ui_utils.py          # UI helper functions (paths, assets)
│
├── imslib/                      # teacher-provided helper modules
│
├── assets/                      # things that ship WITH the app 
│   ├── README.md                
│   ├── animals/                 # premade/gen-AI animal bases 
│   ├── audio_presets/           # built-in sounds 
│   └── ui_images/               # <--- Add this new folder for PNGs           
│
└── data/                        # runtime user-generated stuff
    ├── projects/                # saved garden compositions
    ├── recordings/              # recorded .wav files from the mic
    ├── animals/                 # generated animal configs per user sound
    └── loops/                   # saved loop settings per animal
 ```
