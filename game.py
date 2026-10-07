import pygame
import random
import math
import time

WIDTH, HEIGHT = 800, 560
FPS = 60
BG = (30, 35, 25)
HUD_H = 64

# ---- Tunable constants -----------------------------------------------------
PLAYER_MAX_HP = 3
INVINCIBLE_MS = 1500        # Task 1: invincibility window after a hit
CLIP_SIZE = 12              # Task 2: bullets per clip
RELOAD_MS = 2000            # Task 2: reload duration
NUM_BARRELS = 4             # Task 3
BARREL_RADIUS = 110         # Task 3: explosion radius (pixels)
EXPLOSION_MS = 350          # Task 3: explosion animation length


# ---------------------------------------------------------------------------
# Zombies (Task 4: Zombie base class + Fast + Tank subtypes)
# ---------------------------------------------------------------------------
class Zombie:
    SPEED = 1.5
    HP = 3
    SIZE = 30
    COLOR = (60, 140, 60)
    EYE_R = 4
    WEIGHT = 55             # relative spawn weight

    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, self.SIZE, self.SIZE)
        # float position so slow speeds (< 1 px/frame) still move
        self.fx, self.fy = float(x), float(y)
        self.color = self.COLOR
        self.hp = self.HP
        self.wobble = random.uniform(0, 6.28)
        self.frame = 0

    def update(self, player_pos):
        px, py = player_pos
        cx, cy = self.rect.center
        dx, dy = px - cx, py - cy
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist:
            self.fx += dx / dist * self.SPEED
            self.fy += dy / dist * self.SPEED
            self.rect.x = int(self.fx)
            self.rect.y = int(self.fy)
        self.frame += 1

    def hit(self):
        self.hp -= 1
        return self.hp <= 0

    def draw(self, screen):
        wobble_y = int(math.sin(self.frame * 0.2) * 3)
        draw_rect = self.rect.move(0, wobble_y)
        pygame.draw.rect(screen, self.color, draw_rect, border_radius=5)
        off1, off2 = self.SIZE * 0.2, self.SIZE * 0.6
        for ex in (draw_rect.x + off1, draw_rect.x + off2):
            pygame.draw.circle(screen, (200, 40, 40),
                               (int(ex), draw_rect.y + int(self.SIZE * 0.33)), self.EYE_R)
        # health bar for multi-HP zombies that have taken damage
        if self.HP > 1 and self.hp < self.HP:
            w = self.rect.width
            pygame.draw.rect(screen, (90, 20, 20), (draw_rect.x, draw_rect.y - 8, w, 4))
            pygame.draw.rect(screen, (60, 220, 60),
                             (draw_rect.x, draw_rect.y - 8, int(w * self.hp / self.HP), 4))


class FastZombie(Zombie):
    SPEED = 3.0
    HP = 1
    SIZE = 20
    COLOR = (200, 200, 50)
    EYE_R = 3
    WEIGHT = 27


class TankZombie(Zombie):
    SPEED = 0.8
    HP = 6
    SIZE = 48
    COLOR = (110, 40, 120)
    EYE_R = 6
    WEIGHT = 18


ZOMBIE_TYPES = [Zombie, FastZombie, TankZombie]


def spawn_zombie(width, height, player_rect, margin=120):
    cls = random.choices(ZOMBIE_TYPES, weights=[c.WEIGHT for c in ZOMBIE_TYPES])[0]
    while True:
        x = random.randint(0, width - cls.SIZE)
        y = random.randint(HUD_H, height - cls.SIZE)
        rect = pygame.Rect(x, y, cls.SIZE, cls.SIZE)
        if not rect.colliderect(player_rect.inflate(margin, margin)):
            return cls(x, y)


# ---------------------------------------------------------------------------
# Barrels (Task 3)
# ---------------------------------------------------------------------------
class Barrel:
    W, H = 28, 38

    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, self.W, self.H)

    def draw(self, screen):
        pygame.draw.rect(screen, (170, 50, 30), self.rect, border_radius=6)
        pygame.draw.rect(screen, (230, 170, 40), self.rect, width=2, border_radius=6)
        pygame.draw.line(screen, (230, 170, 40), (self.rect.left, self.rect.centery),
                         (self.rect.right, self.rect.centery), 2)
        # hazard dot
        pygame.draw.circle(screen, (255, 230, 80), self.rect.center, 4)


class Explosion:
    """Purely visual: an expanding ring that fades out."""

    def __init__(self, pos):
        self.pos = pos
        self.start = pygame.time.get_ticks()

    def alive(self):
        return pygame.time.get_ticks() - self.start < EXPLOSION_MS

    def draw(self, screen):
        t = (pygame.time.get_ticks() - self.start) / EXPLOSION_MS
        r = int(BARREL_RADIUS * min(1.0, 0.3 + t))
        surf = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
        alpha = int(200 * (1 - t))
        pygame.draw.circle(surf, (255, 140, 30, alpha), (r, r), r)
        pygame.draw.circle(surf, (255, 240, 120, min(255, alpha + 40)), (r, r), r, 4)
        screen.blit(surf, (self.pos[0] - r, self.pos[1] - r))


def spawn_barrels(count, player_rect):
    barrels = []
    attempts = 0
    while len(barrels) < count and attempts < 1000:
        attempts += 1
        x = random.randint(40, WIDTH - 40 - Barrel.W)
        y = random.randint(HUD_H + 20, HEIGHT - 40 - Barrel.H)
        b = Barrel(x, y)
        if b.rect.colliderect(player_rect.inflate(160, 160)):
            continue
        if any(b.rect.colliderect(o.rect.inflate(80, 80)) for o in barrels):
            continue
        barrels.append(b)
    return barrels


# ---------------------------------------------------------------------------
# Player (Task 1 health + Task 2 ammo)
# ---------------------------------------------------------------------------
SPEED = 4


class Player:
    def __init__(self, x, y):
        self.rect = pygame.Rect(x, y, 32, 32)
        self.color = (60, 160, 220)
        self.bullets = []
        self.shoot_cooldown = 0
        # Task 1
        self.hp = PLAYER_MAX_HP
        self.invincible_until = 0
        # Task 2
        self.ammo = CLIP_SIZE
        self.reloading = False
        self.reload_end = 0

    # -- health ------------------------------------------------------------
    def is_invincible(self):
        return pygame.time.get_ticks() < self.invincible_until

    def take_hit(self):
        """Returns True if damage was actually applied."""
        if self.is_invincible():
            return False
        self.hp -= 1
        self.invincible_until = pygame.time.get_ticks() + INVINCIBLE_MS
        return True

    # -- ammo --------------------------------------------------------------
    def start_reload(self):
        if self.reloading or self.ammo == CLIP_SIZE:
            return
        self.reloading = True
        self.reload_end = pygame.time.get_ticks() + RELOAD_MS

    def reload_remaining_ms(self):
        return max(0, self.reload_end - pygame.time.get_ticks())

    def update_reload(self):
        if self.reloading and pygame.time.get_ticks() >= self.reload_end:
            self.reloading = False
            self.ammo = CLIP_SIZE

    # -- movement / shooting -----------------------------------------------
    def move(self, keys, width, height):
        dx = dy = 0
        if keys[pygame.K_w] or keys[pygame.K_UP]: dy = -SPEED
        if keys[pygame.K_s] or keys[pygame.K_DOWN]: dy = SPEED
        if keys[pygame.K_a] or keys[pygame.K_LEFT]: dx = -SPEED
        if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx = SPEED
        self.rect.x = max(0, min(width - self.rect.width, self.rect.x + dx))
        self.rect.y = max(HUD_H, min(height - self.rect.height, self.rect.y + dy))
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1
        self.update_reload()

    def shoot(self, target_pos):
        if self.reloading:
            return
        if self.ammo <= 0:
            self.start_reload()
            return
        if self.shoot_cooldown > 0:
            return
        cx, cy = self.rect.center
        tx, ty = target_pos
        dx, dy = tx - cx, ty - cy
        dist = (dx ** 2 + dy ** 2) ** 0.5
        if dist == 0:
            return
        vx, vy = dx / dist * 10, dy / dist * 10
        self.bullets.append([cx - 4, cy - 4, vx, vy])
        self.shoot_cooldown = 15
        self.ammo -= 1
        if self.ammo == 0:
            self.start_reload()     # auto-reload when the clip runs dry

    def update_bullets(self, width, height):
        live = []
        for b in self.bullets:
            b[0] += b[2]; b[1] += b[3]
            if 0 <= b[0] <= width and 0 <= b[1] <= height:
                live.append(b)
        self.bullets = live

    def draw(self, screen):
        # blink while invincible
        if not (self.is_invincible() and (pygame.time.get_ticks() // 100) % 2 == 0):
            pygame.draw.rect(screen, self.color, self.rect, border_radius=6)
        if self.is_invincible():
            pygame.draw.rect(screen, (255, 255, 255), self.rect.inflate(8, 8), width=2, border_radius=8)
        for b in self.bullets:
            pygame.draw.circle(screen, (255, 220, 60), (int(b[0]), int(b[1])), 5)


# ---------------------------------------------------------------------------
# Game engine
# ---------------------------------------------------------------------------
class GameEngine:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Zombie Escape")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("monospace", 22)
        self.big_font = pygame.font.SysFont("monospace", 44, bold=True)
        self.reset()

    def reset(self):
        self.player = Player(WIDTH // 2, HEIGHT // 2)
        self.zombies = [spawn_zombie(WIDTH, HEIGHT, self.player.rect) for _ in range(4)]
        self.barrels = spawn_barrels(NUM_BARRELS, self.player.rect)
        self.explosions = []
        self.score = 0
        self.kill_points = 0
        self.wave = 1
        self.kills = 0
        self.kills_to_next = 8
        self.game_over = False
        self.start_time = time.time()

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_r: self.reset()
            if event.type == pygame.MOUSEBUTTONDOWN and not self.game_over:
                self.player.shoot(event.pos)
        return True

    # -- helpers -------------------------------------------------------------
    def register_kill(self, z):
        if z in self.zombies:
            self.zombies.remove(z)
            self.kills += 1
            self.kill_points += 10

    def explode_barrel(self, barrel):
        center = barrel.rect.center
        self.barrels.remove(barrel)
        self.explosions.append(Explosion(center))
        for z in self.zombies[:]:
            zx, zy = z.rect.center
            if math.hypot(zx - center[0], zy - center[1]) <= BARREL_RADIUS:
                self.register_kill(z)

    def update(self):
        if self.game_over: return
        keys = pygame.key.get_pressed()
        self.player.move(keys, WIDTH, HEIGHT)
        self.player.update_bullets(WIDTH, HEIGHT)
        self.score = int(time.time() - self.start_time) + self.kill_points

        # Task 1: damage with invincibility frames
        for z in self.zombies:
            z.update(self.player.rect.center)
            if z.rect.colliderect(self.player.rect):
                self.player.take_hit()
        if self.player.hp <= 0:
            self.player.hp = 0
            self.game_over = True

        # bullets vs barrels (Task 3)
        for barrel in self.barrels[:]:
            for b in self.player.bullets[:]:
                if barrel.rect.collidepoint(int(b[0]), int(b[1])):
                    self.player.bullets.remove(b)
                    self.explode_barrel(barrel)
                    break
        self.explosions = [e for e in self.explosions if e.alive()]

        # bullets vs zombies
        dead = []
        for z in self.zombies:
            for b in self.player.bullets[:]:
                bx, by = int(b[0]), int(b[1])
                if z.rect.collidepoint(bx, by):
                    if z.hit():
                        dead.append(z)
                    if b in self.player.bullets:
                        self.player.bullets.remove(b)
        for z in dead:
            self.register_kill(z)

        if self.kills >= self.kills_to_next:
            self.kills = 0
            self.wave += 1
            self.kills_to_next = 8 + self.wave * 2
            for _ in range(self.wave + 3):
                self.zombies.append(spawn_zombie(WIDTH, HEIGHT, self.player.rect))

    def draw_hud(self):
        pygame.draw.rect(self.screen, (15, 20, 15), pygame.Rect(0, 0, WIDTH, HUD_H))
        line1 = self.font.render(
            f"Wave: {self.wave}  Score: {self.score}  Kills: {self.kills}/{self.kills_to_next}",
            True, (160, 220, 120))
        self.screen.blit(line1, (8, 6))
        # HP hearts
        hp_label = self.font.render("HP:", True, (230, 90, 90))
        self.screen.blit(hp_label, (8, 34))
        for i in range(PLAYER_MAX_HP):
            col = (220, 50, 50) if i < self.player.hp else (70, 30, 30)
            pygame.draw.circle(self.screen, col, (70 + i * 26, 46), 9)
        # Ammo / reload
        if self.player.reloading:
            secs = self.player.reload_remaining_ms() / 1000
            ammo_txt = f"Ammo: RELOADING {secs:.1f}s"
            col = (255, 180, 60)
        else:
            ammo_txt = f"Ammo: {self.player.ammo}/{CLIP_SIZE}"
            col = (255, 230, 100)
        self.screen.blit(self.font.render(ammo_txt, True, col), (180, 34))
        hint = self.font.render("R: Restart", True, (110, 150, 90))
        self.screen.blit(hint, (WIDTH - hint.get_width() - 8, 6))

    def draw(self):
        self.screen.fill(BG)
        for x in range(0, WIDTH, 60):
            pygame.draw.line(self.screen, (40, 45, 35), (x, 0), (x, HEIGHT), 1)
        for y in range(0, HEIGHT, 60):
            pygame.draw.line(self.screen, (40, 45, 35), (0, y), (WIDTH, y), 1)
        for barrel in self.barrels: barrel.draw(self.screen)
        for z in self.zombies: z.draw(self.screen)
        self.player.draw(self.screen)
        for e in self.explosions: e.draw(self.screen)
        self.draw_hud()

        if self.game_over:
            ov = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            self.screen.blit(ov, (0, 0))
            m = self.big_font.render("DEVOURED!", True, (180, 40, 40))
            s = self.font.render(f"Wave {self.wave} | Score {self.score} | Press R", True, (200, 200, 200))
            self.screen.blit(m, (WIDTH // 2 - m.get_width() // 2, HEIGHT // 2 - 40))
            self.screen.blit(s, (WIDTH // 2 - s.get_width() // 2, HEIGHT // 2 + 20))

        pygame.display.flip()

    def run(self):
        running = True
        while running:
            running = self.handle_events()
            self.update()
            self.draw()
            self.clock.tick(FPS)
        pygame.quit()


if __name__ == "__main__":
    engine = GameEngine()
    engine.run()