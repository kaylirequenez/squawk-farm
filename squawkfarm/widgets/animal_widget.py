import os
import random

from kivy.uix.image import Image
from kivy.uix.button import Button
from kivy.clock import Clock
from kivy.core.window import Window

TERRAIN_BOUNDARY_RATIO = 0.363


class AnimalWidget(Image):
    def __init__(self, animal, on_click_callback=None, on_drag_end_callback=None, **kwargs):
        self.animal = animal
        self.on_click_callback = on_click_callback
        self.on_drag_end_callback = on_drag_end_callback

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

        self._center_x = 0.0
        self._center_y = 0.0

        # Dragging state
        self._is_dragging = False
        self._drag_touch = None
        self._drag_start_pos = None
        self._drag_offset = (0, 0)
        self._drag_threshold = 10  # pixels before drag starts

        kwargs.setdefault("size_hint", (None, None))
        super().__init__(**kwargs)

        self.click_button_scale = 1.5
        self.click_button = Button(
            size_hint=(None, None),
            background_color=(0, 0, 0, 0),
            background_normal='',
        )
        self.click_button.bind(
            on_touch_down=self._on_touch_down,
            on_touch_move=self._on_touch_move,
            on_touch_up=self._on_touch_up,
        )
        
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
                if self._center_x != 0.0 or self._center_y != 0.0:
                    new_x, new_y = self._update_shadow_pos(self._center_x, self._center_y)
                    self.pos = (new_x, new_y)
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
    
    def _on_touch_down(self, button, touch):
        if not button.collide_point(*touch.pos):
            return False
        
        # Stop wandering when touched
        self._wander_state = "idle"
        self._wander_target = None
        self._move_start_pos = None
        
        # Start tracking for potential drag
        self._drag_touch = touch
        self._drag_start_pos = (touch.x, touch.y)
        # Store the offset from touch to animal center so we can maintain it during drag
        self._drag_offset = (touch.x - self._center_x, touch.y - self._center_y)
        self._is_dragging = False
        touch.grab(button)
        return True
    
    def _on_touch_move(self, button, touch):
        if touch.grab_current != button:
            return False
        
        if self._drag_touch != touch:
            return False
        
        # Check if we've moved enough to start dragging
        if self._drag_start_pos:
            dx = abs(touch.x - self._drag_start_pos[0])
            dy = abs(touch.y - self._drag_start_pos[1])
            if dx > self._drag_threshold or dy > self._drag_threshold:
                self._is_dragging = True
        
        if self._is_dragging:
            # Calculate new center position from touch, accounting for the initial offset
            off_x, off_y = self._drag_offset
            new_center_x = touch.x - off_x
            new_center_y = touch.y - off_y
            
            # Apply bounds constraints - get current window size dynamically for resize support
            width, height = Window.size
            
            # Allow movement across full screen (x=0 to x=width, y=0 to terrain boundary)
            min_center_x = 0
            max_center_x = width
            
            # Y bounds: from very bottom of screen (y=0) to terrain boundary
            max_center_y = height * TERRAIN_BOUNDARY_RATIO
            min_center_y = 0
            
            # Clamp to bounds
            new_center_x = max(min_center_x, min(new_center_x, max_center_x))
            new_center_y = max(min_center_y, min(new_center_y, max_center_y))
            
            # Update position
            self._center_x = new_center_x
            self._center_y = new_center_y
            new_x, new_y = self._update_shadow_pos(self._center_x, self._center_y)
            self.pos = (new_x, new_y)
            
            # Update animal model position
            ground_x = self._center_x - self._base_width / 2
            ground_y = self._center_y - self._base_height / 2
            self.animal.pos = (ground_x, ground_y)
        
        return True
    
    def _on_touch_up(self, button, touch):
        if touch.grab_current != button:
            return False
        
        touch.ungrab(button)
        
        if self._drag_touch != touch:
            return False
        
        was_dragging = self._is_dragging
        
        # Reset drag state
        self._drag_touch = None
        self._drag_start_pos = None
        self._is_dragging = False
        
        # If we weren't dragging, it's a click - trigger callback
        if not was_dragging:
            if self.on_click_callback:
                self.on_click_callback(self.animal.animal_id)
        else:
            # After drag, notify the callback with final position
            if self.on_drag_end_callback:
                self.on_drag_end_callback(self.animal.animal_id, self._center_x, self._center_y)
            # Reset wander pause so animal doesn't immediately walk away
            self._wander_pause_remaining = random.uniform(2.0, 5.0)
        
        return True
    
    def move_to(self, pos):
        ground_x, ground_y = pos
        self._center_x = ground_x + self._base_width / 2
        self._center_y = ground_y + self._base_height / 2
        new_x, new_y = self._update_shadow_pos(self._center_x, self._center_y)
        self.pos = (new_x, new_y)

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
            ground_x, ground_y = animal.pos
            self._center_x = ground_x + self._base_width / 2
            self._center_y = ground_y + self._base_height / 2

        self._update_image()
        self._update_shadow_image()
        new_x, new_y = self._update_shadow_pos(self._center_x, self._center_y)
        self.pos = (new_x, new_y)

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

    def _update_shadow_pos(self, center_x, center_y):
        from kivy.core.window import Window
        max_y = Window.height * TERRAIN_BOUNDARY_RATIO

        y_ratio = center_y / max_y if max_y > 0 else 0.0
        y_ratio = max(0.0, min(1.0, y_ratio))

        scale = 1.0 - 0.5 * y_ratio

        scaled_width = self._base_width * scale
        scaled_height = self._base_height * scale

        new_x = center_x - scaled_width / 2
        new_y = center_y - scaled_height / 2

        self.size = (scaled_width, scaled_height)

        if self.shadow_image is not None:
            self.shadow_image.size = (scaled_width, scaled_height)
            self.shadow_image.pos = (new_x, new_y)

        if hasattr(self, 'click_button'):
            base_size = self.animal.size if self.animal.size is not None else (100.0, 100.0)
            w, h = base_size
            size_scale = max(1.0, w / 100.0) * scale
            btn_w = w * self.click_button_scale * size_scale
            btn_h = h * self.click_button_scale * size_scale
            self.click_button.size = (btn_w, btn_h)
            self.click_button.pos = (new_x + (scaled_width - btn_w) / 2, new_y + (scaled_height - btn_h) * 0.6)

        return new_x, new_y

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
        x, y = self._center_x, self._center_y

        max_center_y = height * TERRAIN_BOUNDARY_RATIO - self._hop_height
        min_center_y = self._base_height * 1.0 / 2

        tx = random.uniform(self._base_width / 2, width - self._base_width / 2)
        ty = random.uniform(min_center_y, max(min_center_y, max_center_y))

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
        # Don't update wander while being dragged
        if self._is_dragging or self._drag_touch is not None:
            return

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
                new_x, new_y = self._update_shadow_pos(self._center_x, self._center_y)
                self.pos = (new_x, new_y)

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

            center_x = base_x
            center_y = base_y

            self._center_x = center_x
            self._center_y = center_y + hop_offset

            adjusted_x, adjusted_y = self._update_shadow_pos(self._center_x, self._center_y)

            self.pos = (adjusted_x, adjusted_y)

            if t >= 1.0:
                self._wander_state = "idle"
                self._wander_pause_remaining = random.uniform(1.0, 9.0)
                self._wander_target = None
                self._move_start_pos = None
                self._move_duration = 0.0
                self._move_elapsed = 0.0
                self._segment_count = 1

