import os
import random
from typing import Tuple, Dict, Optional

from kivy.uix.image import Image
from kivy.clock import Clock

from ..models.animal import Animal


class AnimalWidget(Image):
    def __init__(self, animal: Animal, on_click_callback=None, **kwargs):
        self.animal = animal
        self.on_click_callback = on_click_callback

        self.sprite_paths: Dict[Tuple[str, str], str] = self._derive_sprite_paths(
            animal.image_path
        )
        self.shadow_paths: Dict[Tuple[str, str], str] = self._derive_shadow_paths(
            animal.image_path
        )
        self.shadow_image: Optional[Image] = None
        self._last_parent = None

        self.wander_speed: float = kwargs.pop("wander_speed", 40.0)
        self._wander_state: str = "idle"
        self._wander_pause_remaining: float = random.uniform(1.0, 9.0)
        self._wander_target: Optional[Tuple[float, float]] = None
        self._wander_move_count: int = 0

        self._move_start_pos: Optional[Tuple[float, float]] = None
        self._move_duration: float = 0.0
        self._move_elapsed: float = 0.0
        self._hop_height: float = kwargs.pop("hop_height", 40.0)
        self._segment_count: int = 1

        self._facing: str = "right"
        self._mouth_state: str = "closed"

        kwargs.setdefault("size_hint", (None, None))
        super().__init__(**kwargs)
        self.update_from_animal(animal)

    def _derive_sprite_paths(self, image_path: str) -> Dict[Tuple[str, str], str]:
        if image_path.endswith("open.png"):
            base = image_path[: -len("open.png")]
            open_right = image_path
            closed_right = base + "closed.png"
        elif image_path.endswith("closed.png"):
            base = image_path[: -len("closed.png")]
            closed_right = image_path
            open_right = base + "open.png"
        else:
            dot = image_path.rfind(".")
            base = image_path[:dot] if dot != -1 else image_path
            closed_right = image_path
            open_right = image_path

        open_left_candidate = base + "open_left.png"
        closed_left_candidate = base + "closed_left.png"

        if os.path.exists(open_left_candidate):
            open_left = open_left_candidate
        else:
            open_left = open_right

        if os.path.exists(closed_left_candidate):
            closed_left = closed_left_candidate
        else:
            closed_left = closed_right

        return {
            ("right", "open"): open_right,
            ("right", "closed"): closed_right,
            ("left", "open"): open_left,
            ("left", "closed"): closed_left,
        }

    def _derive_shadow_paths(self, image_path: str) -> Dict[Tuple[str, str], str]:
        dir_name = os.path.dirname(image_path)
        filename = os.path.basename(image_path)

        if filename.endswith("open.png"):
            base = filename[: -len("open.png")]
            open_right = filename
            closed_right = base + "closed.png"
        elif filename.endswith("closed.png"):
            base = filename[: -len("closed.png")]
            closed_right = filename
            open_right = base + "open.png"
        else:
            dot = filename.rfind(".")
            base = filename[:dot] if dot != -1 else filename
            closed_right = filename
            open_right = filename

        shadow_dir = os.path.join(dir_name, "shadow")

        def shadow_path(name: str) -> str:
            return os.path.join(shadow_dir, name)

        open_left_candidate = base + "open_left.png"
        closed_left_candidate = base + "closed_left.png"

        if os.path.exists(shadow_path(open_left_candidate)):
            open_left = open_left_candidate
        else:
            open_left = open_right

        if os.path.exists(shadow_path(closed_left_candidate)):
            closed_left = closed_left_candidate
        else:
            closed_left = closed_right

        return {
            ("right", "open"): shadow_path(open_right),
            ("right", "closed"): shadow_path(closed_right),
            ("left", "open"): shadow_path(open_left),
            ("left", "closed"): shadow_path(closed_left),
        }

    def on_parent(self, instance, parent):
        if parent is not None:
            if self.shadow_image is None:
                self.shadow_image = Image(size_hint=(None, None))
                parent.add_widget(self.shadow_image, index=0)
                self.shadow_image.size = self.size
                self._update_shadow_image()
                self._update_shadow_pos(self.x, self.y)
        else:
            if self._last_parent is not None and self.shadow_image is not None:
                try:
                    self._last_parent.remove_widget(self.shadow_image)
                except Exception:
                    pass
                self.shadow_image = None

        self._last_parent = parent

    def update_from_animal(self, animal: Animal):
        self.animal = animal
        self.sprite_paths = self._derive_sprite_paths(animal.image_path)
        self.shadow_paths = self._derive_shadow_paths(animal.image_path)

        base_size = animal.size if animal.size is not None else (100.0, 100.0)
        w, h = base_size
        self.size = (w * 3.0, h * 3.0)

        if animal.pos is not None:
            self.pos = animal.pos

        if self.shadow_image is not None:
            self.shadow_image.size = self.size

        self._update_image()
        self._update_shadow_image()
        self._update_shadow_pos(self.x, self.y)

    def _update_image(self):
        key = (self._facing, self._mouth_state)
        path = self.sprite_paths.get(key)

        if path is None:
            path = self.sprite_paths.get(("right", "closed"), "")

        if path and self.source != path:
            self.source = path
            self.reload()

    def _update_shadow_image(self):
        if self.shadow_image is None:
            return

        key = (self._facing, self._mouth_state)
        path = self.shadow_paths.get(key)

        if not os.path.exists(path or ""):
            path = self.shadow_paths.get(("right", "closed"), "")

        if path and self.shadow_image.source != path:
            self.shadow_image.source = path
            self.shadow_image.reload()

    def _update_shadow_pos(self, ground_x: float, ground_y: float):
        if self.shadow_image is None:
            return

        self.shadow_image.size = self.size
        self.shadow_image.pos = (ground_x, ground_y)

    def _set_facing(self, facing: str):
        if facing not in ("right", "left"):
            return
        if facing == self._facing:
            return
        self._facing = facing
        self._update_image()
        self._update_shadow_image()

    def open_mouth(self):
        if self._mouth_state == "open":
            return
        self._mouth_state = "open"
        self._update_image()
        self._update_shadow_image()

    def close_mouth(self):
        if self._mouth_state == "closed":
            return
        self._mouth_state = "closed"
        self._update_image()
        self._update_shadow_image()

    def speak_once(self, duration: float = 0.25):
        self.open_mouth()
        Clock.schedule_once(lambda dt: self.close_mouth(), duration)

    def move_to(self, pos: Tuple[float, float]):
        self.pos = pos
        self._update_shadow_pos(*pos)

    def move_by(self, dx: float, dy: float):
        x, y = self.pos
        new_pos = (x + dx, y + dy)
        self.pos = new_pos
        self._update_shadow_pos(*new_pos)

    def _start_new_move(self, bounds: Tuple[int, int]):
        width, height = bounds
        margin = 10
        max_x = max(margin, width - self.width - margin)
        max_y = max(margin, height - self.height - margin)

        x, y = self.pos
        base_step = 50.0 * 3.0

        if random.random() < 1.0 / 4.5:
            max_step = base_step * 5.0
        else:
            max_step = base_step

        tx = x + random.uniform(-max_step, max_step)
        ty = y + random.uniform(-max_step, max_step)

        tx = min(max(margin, tx), max_x)
        ty = min(max(margin, ty), max_y)

        dx = tx - x
        dy = ty - y
        dist_sq = dx * dx + dy * dy

        if dist_sq == 0:
            self._wander_state = "idle"
            self._wander_pause_remaining = random.uniform(1.0, 9.0)
            self._wander_target = None
            self._move_start_pos = None
            self._move_duration = 0.0
            self._move_elapsed = 0.0
            self._segment_count = 1
            return

        dist = dist_sq ** 0.5

        base_duration = dist / max(self.wander_speed, 1e-6)
        self._move_duration = max(base_duration * 1.1, 0.2)

        self._hop_height = max(30.0, min(90.0, dist * 0.12))

        approx_segments = dist / 130.0 if dist > 0 else 1.0
        raw_segments = int(round(approx_segments)) or 1
        self._segment_count = max(3, min(9, raw_segments))

        self._wander_target = (tx, ty)
        self._wander_state = "moving"
        self._move_start_pos = (x, y)
        self._move_elapsed = 0.0
        self._wander_move_count += 1

    def update_wander(self, dt: float, bounds: Tuple[int, int]):
        width, height = bounds

        if self.width == 0 or self.height == 0:
            return

        if self._wander_state == "idle":
            self._wander_pause_remaining -= dt
            if self._wander_pause_remaining <= 0:
                self._start_new_move(bounds)
            else:
                self._update_shadow_pos(self.x, self.y)

        elif (
            self._wander_state == "moving"
            and self._wander_target is not None
            and self._move_start_pos is not None
        ):
            self._move_elapsed += dt
            t = min(1.0, self._move_elapsed / max(self._move_duration, 1e-6))

            sx, sy = self._move_start_pos
            tx, ty = self._wander_target

            base_x = sx + (tx - sx) * t
            base_y = sy + (ty - sy) * t

            dx_total = tx - sx
            if dx_total < 0:
                self._set_facing("left")
            elif dx_total > 0:
                self._set_facing("right")

            if t >= 1.0 or self._segment_count <= 1:
                hop_offset = 0.0
            else:
                seg_len = 1.0 / float(self._segment_count)
                seg_phase = (t % seg_len) / seg_len
                hop_offset = self._hop_height * 4.0 * seg_phase * (1.0 - seg_phase)

            margin = 10
            max_x = max(margin, width - self.width - margin)
            max_ground_y = max(margin, height - self.height - margin)

            ground_x = min(max(margin, base_x), max_x)
            ground_y = min(max(margin, base_y), max_ground_y)

            max_y = max_ground_y
            final_x = ground_x
            final_y = min(max(margin, ground_y + hop_offset), max_y + hop_offset)

            self._update_shadow_pos(ground_x, ground_y)
            self.pos = (final_x, final_y)

            if t >= 1.0:
                self._wander_state = "idle"
                self._wander_pause_remaining = random.uniform(1.0, 9.0)
                self._wander_target = None
                self._move_start_pos = None
                self._move_duration = 0.0
                self._move_elapsed = 0.0
                self._segment_count = 1

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if self.on_click_callback:
                self.on_click_callback(self.animal.animal_id)
            return True
        return super().on_touch_down(touch)
