# carousel.py

from gi.repository import Gtk, Adw, GLib, Gdk

@Gtk.Template(resource_path='/com/jeffser/Nocturne/containers/carousel.ui')
class Carousel(Gtk.Box):
    __gtype_name__ = 'NocturneCarousel'

    header_button = Gtk.Template.Child()
    previous_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()
    scrolled_el = Gtk.Template.Child()
    list_el = Gtk.Template.Child()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scroll_animation_source = None
        adjustment = self.scrolled_el.get_hadjustment()
        adjustment.connect('value-changed', self.update_pagination)
        adjustment.connect('notify::upper', self.update_pagination)
        adjustment.connect('notify::page-size', self.update_pagination)
        GLib.idle_add(self.update_pagination)

    def do_measure(self, orientation, for_size):
        minimum, natural, minimum_baseline, natural_baseline = super().do_measure(orientation, for_size)
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 0, 0, minimum_baseline, natural_baseline
        return minimum, natural, minimum_baseline, natural_baseline

    def set_header(self, label:str, icon_name:str, page_tag:str=None):
        self.header_button.set_tooltip_text(label)
        self.header_button.get_child().set_label(label)
        self.header_button.get_child().set_icon_name(icon_name)
        self.header_button.set_visible(True)
        if page_tag:
            self.header_button.set_action_target_value(GLib.Variant.new_string(page_tag))
            self.header_button.set_action_name('app.replace_root_page')

    def remove_all(self):
        child = self.list_el.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.list_el.remove(child)
            child = next_child

    def set_widgets(self, widgets:list):
        def update_widgets():
            self.cancel_scroll_animation()
            self.remove_all()
            self.set_visible(len(widgets) > 0)
            for widget in widgets:
                self.list_el.append(widget)
            self.scrolled_el.get_hadjustment().set_value(0)
            GLib.idle_add(self.update_pagination)
            return GLib.SOURCE_REMOVE

        GLib.idle_add(update_widgets)

    def cancel_scroll_animation(self):
        if self._scroll_animation_source:
            GLib.source_remove(self._scroll_animation_source)
            self._scroll_animation_source = None

    def update_pagination(self, *args):
        adjustment = self.scrolled_el.get_hadjustment()
        value = adjustment.get_value()
        upper = max(0, adjustment.get_upper() - adjustment.get_page_size())
        has_overflow = upper > 1
        at_start = value <= 1
        at_end = value >= upper - 1

        self.previous_button.set_visible(has_overflow)
        self.next_button.set_visible(has_overflow)
        self.previous_button.set_sensitive(has_overflow)
        self.next_button.set_sensitive(has_overflow)
        self.previous_button.set_opacity(0.35 if at_start else 1)
        self.next_button.set_opacity(0.35 if at_end else 1)
        return GLib.SOURCE_REMOVE

    def animate_scroll_to(self, target:float, duration:int=220):
        adjustment = self.scrolled_el.get_hadjustment()
        upper = max(0, adjustment.get_upper() - adjustment.get_page_size())
        target = max(0, min(target, upper))
        start = adjustment.get_value()

        self.cancel_scroll_animation()

        if abs(target - start) < 1:
            adjustment.set_value(target)
            self.update_pagination()
            return

        start_time = GLib.get_monotonic_time()

        def tick():
            elapsed = GLib.get_monotonic_time() - start_time
            progress = min(1, elapsed / (duration * 1000))
            eased = 1 - pow(1 - progress, 3)
            adjustment.set_value(start + ((target - start) * eased))

            if progress >= 1:
                self._scroll_animation_source = None
                self.update_pagination()
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        self._scroll_animation_source = GLib.timeout_add(16, tick)

    def scroll_by_page(self, direction:int):
        adjustment = self.scrolled_el.get_hadjustment()
        upper = max(0, adjustment.get_upper() - adjustment.get_page_size())
        page_delta = max(240, adjustment.get_page_size() - 80)
        value = adjustment.get_value() + (page_delta * direction)
        self.animate_scroll_to(max(0, min(value, upper)))

    @Gtk.Template.Callback()
    def scroll_previous(self, button):
        self.scroll_by_page(-1)

    @Gtk.Template.Callback()
    def scroll_next(self, button):
        self.scroll_by_page(1)

    @Gtk.Template.Callback()
    def on_scroll(self, controller, dx, dy):
        event = controller.get_current_event()
        state = event.get_modifier_state() if event else 0
        if dx or (dy and (state & Gdk.ModifierType.SHIFT_MASK)):
            self.cancel_scroll_animation()
            adjustment = self.scrolled_el.get_hadjustment()
            upper = max(0, adjustment.get_upper() - adjustment.get_page_size())
            delta = dx if dx else dy * (adjustment.get_step_increment() or 30) * 4
            adjustment.set_value(max(0, min(adjustment.get_value() + delta, upper)))
            return Gdk.EVENT_STOP
        return Gdk.EVENT_PROPAGATE
