import os
import random

from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window


class AnimalWidget(Image):
    def __init__(self, animal, on_click_callback=None, **kwargs):
        self.animal = animal
        self.on_click_callback = on_click_callback

        self.sprite_paths = self._derive_sprite_paths(animal.image_path)
        self.shadow_paths = self._derive_shadow_paths(animal.image_path)
        self.shadow_image = None
        self._last_parent = None

        self.wander_speed = kwargs.pop("wander_speed", 40.0)
        self._wander_state = "idle"
        self._wander_pause_remaining = random.uniform(1.0, 9.0)
        self._wander_target = None
        self._wander_move_count = 0

        self._move_start_pos = None
        self._move_duration = 0.0
        self._move_elapsed = 0.0
        self._hop_height = kwargs.pop("hop_height", 40.0)
        self._segment_count = 1

        self._facing = "right"
        self._mouth_state = "closed"

        base_size = animal.size if animal.size is not None else (100.0, 100.0)
        self._base_width = base_size[0] * 8.0
        self._base_height = base_size[1] * 8.0

        kwargs.setdefault("size_hint", (None, None))
        super().__init__(**kwargs)

        self.click_button_scale = 1.5
        self.click_button = Button(
            size_hint=(None, None),
            background_color=(0, 0, 0, 0),
            background_normal='',
        )
        self.click_button.bind(on_press=self._on_click_button_press)
        
        self.update_from_animal(animal)

    def _derive_sprite_paths(self, image_path):
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

    def _derive_shadow_paths(self, image_path):
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

        def shadow_path(name):
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
            parent.add_widget(self.click_button)
            if self.shadow_image is None:
                self.shadow_image = Image(size_hint=(None, None))
                parent.add_widget(self.shadow_image, index=0)
                self.shadow_image.size = self.size
                self._update_shadow_image()
                self._update_shadow_pos(self.x, self.y)
        else:
            if self._last_parent is not None:
                if self.click_button in self._last_parent.children:
                    try:
                        self._last_parent.remove_widget(self.click_button)
                    except Exception:
                        pass
                if self.shadow_image is not None:
                    try:
                        self._last_parent.remove_widget(self.shadow_image)
                    except Exception:
                        pass
                    self.shadow_image = None

        self._last_parent = parent
    
    def _on_click_button_press(self, instance):
        if self.on_click_callback:
            self.on_click_callback(self.animal.animal_id)
    
    def move_to(self, pos):
        self.pos = pos
        self._update_shadow_pos(*pos)

    def update_from_animal(self, animal):
        self.animal = animal
        self.sprite_paths = self._derive_sprite_paths(animal.image_path)
        self.shadow_paths = self._derive_shadow_paths(animal.image_path)

        base_size = animal.size if animal.size is not None else (100.0, 100.0)
        w, h = base_size
        self._base_width = w * 8.0
        self._base_height = h * 8.0
        self.size = (self._base_width, self._base_height)

        if animal.pos is not None:
            self.pos = animal.pos

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

    def _get_perspective_scale(self, ground_y, screen_height):
        bottom_bound = screen_height * 0.08
        top_bound = screen_height / 3

        range_height = top_bound - bottom_bound
        if range_height <= 0:
            return 1.0

        t = (ground_y - bottom_bound) / range_height
        t = max(0.0, min(1.0, t))

        min_scale = 0.33
        max_scale = 1.0
        return max_scale - t * (max_scale - min_scale)

    def _update_shadow_pos(self, ground_x, ground_y):
        scale = self._get_perspective_scale(ground_y, Window.height)

        scaled_w = self._base_width * scale
        scaled_h = self._base_height * scale

        self.size = (scaled_w, scaled_h)

        if self.shadow_image is not None:
            self.shadow_image.size = (scaled_w, scaled_h)
            self.shadow_image.pos = (ground_x, ground_y)

        if hasattr(self, 'click_button'):
            base_size = self.animal.size if self.animal.size is not None else (100.0, 100.0)
            w, h = base_size
            size_scale = max(1.0, w / 100.0)
            btn_w = w * self.click_button_scale * size_scale * scale
            btn_h = h * self.click_button_scale * size_scale * scale
            self.click_button.size = (btn_w, btn_h)
            self.click_button.pos = (ground_x + (scaled_w - btn_w) / 2, ground_y + (scaled_h - btn_h) * 0.6)

    def _set_facing(self, facing):
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

    def speak_once(self, duration=0.25):
        self.open_mouth()
        Clock.schedule_once(lambda dt: self.close_mouth(), duration)

    def move_by(self, dx, dy):
        x, y = self.pos
        new_pos = (x + dx, y + dy)
        self.move_to(new_pos)

    def _collides_with_others(self, tx, ty, others):
        my_w, my_h = self.width, self.height
        for ox, oy, ow, oh in others:
            min_dist_x = (my_w + ow) / 2 * 1.1
            min_dist_y = (my_h + oh) / 2 * 1.1
            cx, cy = tx + my_w / 2, ty + my_h / 2
            ocx, ocy = ox + ow / 2, oy + oh / 2
            if abs(cx - ocx) < min_dist_x and abs(cy - ocy) < min_dist_y:
                return True
        return False

    def _start_new_move(self, bounds, others=None):
        if others is None:
            others = []

        width, height = bounds
        margin = 10
        min_y = height * 0.05
        max_y = height * 0.25

        x, y = self.pos

        tx = random.uniform(margin, width - margin)
        ty = random.uniform(min_y, max_y)

        dx = tx - x
        dy = ty - y
        dist_sq = dx * dx + dy * dy

        if dist_sq == 0:
            self._wander_state = "idle"
            self._wander_pause_remaining = random.uniform(1.0, 3.0)
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

    def update_wander(self, dt, bounds, others=None):
        if others is None:
            others = []
        width, height = bounds

        if self.width == 0 or self.height == 0:
            return

        if self._wander_state == "idle":
            self._wander_pause_remaining -= dt
            if self._wander_pause_remaining <= 0:
                self._start_new_move(bounds, others)
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

            ground_x = base_x
            ground_y = base_y

            final_x = ground_x
            final_y = ground_y + hop_offset

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

