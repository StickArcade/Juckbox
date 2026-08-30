import pygame
import json
import os

class Renderer:
    def __init__(self, screen, theme_path):
        self.screen = screen
        self.theme_path = theme_path
        self.theme = self.load_theme(theme_path)

        self.bg_color = self.theme["background_color"]
        self.text_color = self.theme["text_color"]
        self.highlight_color = self.theme["highlight_color"]

        font_path = self.theme["font"]
        font_size = self.theme["font_size"]

        if font_path:
            full_path = os.path.join(theme_path, font_path)
            self.font = pygame.font.Font(full_path, font_size)
        else:
            self.font = pygame.font.SysFont(None, font_size)

        # Carregar imagem default de playing
        playing_img_path = os.path.join(
            theme_path, "assets", "playing.png"
        )

        if os.path.exists(playing_img_path):
            self.playing_image = pygame.image.load(playing_img_path)
            self.playing_image = pygame.transform.scale(
                self.playing_image,
                self.screen.get_size()
            )
        else:
            self.playing_image = None
