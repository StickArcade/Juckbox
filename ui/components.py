import pygame

class MenuList:
    def __init__(self, items):
        self.items = items
        self.selected_index = 0

    def move_up(self):
        if self.selected_index > 0:
            self.selected_index -= 1

    def move_down(self):
        if self.selected_index < len(self.items) - 1:
            self.selected_index += 1

    def get_selected(self):
        return self.items[self.selected_index]
