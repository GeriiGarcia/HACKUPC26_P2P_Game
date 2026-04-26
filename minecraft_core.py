import math
import random
import time

# --- Constants ---
WORLD_WIDTH = 400
WORLD_HEIGHT = 400

# Blocks
B_AIR = 0
B_DIRT = 1
B_STONE = 2
B_WOOD = 3
B_WHEAT = 4
B_GRASS = 5
B_LEAF = 6
B_SAND = 7
B_FLOWER_RED = 8
B_FLOWER_YELLOW = 9
B_CHEST = 100  # Cofre especial (entidad, no material)

BLOCK_NAMES = {
    B_AIR: "Aire",
    B_DIRT: "Tierra",
    B_STONE: "Piedra",
    B_WOOD: "Madera",
    B_WHEAT: "Trigo",
    B_GRASS: "Hierba",
    B_LEAF: "Hojas",
    B_SAND: "Arena",
    B_FLOWER_RED: "Flor Roja",
    B_FLOWER_YELLOW: "Flor Amarilla",
    B_CHEST: "Cofre",
}

# Items
I_DIRT = 1
I_STONE = 2
I_WOOD = 3
I_WHEAT = 4
I_BREAD = 5
I_MEAT = 6
I_GRASS = 5     # grass drops dirt
I_LEAF = 6      # leaf block item
I_SAND = 7
T_PICKAXE = 10
T_SHOVEL = 11
T_AXE = 12
I_CHEST = 20    # Cofre privado

ITEM_NAMES = {
    I_DIRT: "Tierra",
    I_STONE: "Piedra",
    I_WOOD: "Madera",
    I_WHEAT: "Trigo",
    I_BREAD: "Pan",
    I_MEAT: "Carne",
    I_SAND: "Arena",
    T_PICKAXE: "Pico",
    T_SHOVEL: "Pala",
    T_AXE: "Hacha",
    I_CHEST: "Cofre",
}

# Non-solid blocks (player can walk through)
NON_SOLID = {B_AIR, B_WHEAT, B_FLOWER_RED, B_FLOWER_YELLOW}

# --- World Logic ---
class World:
    def __init__(self, seed=None):
        self.grid = [[B_AIR for _ in range(WORLD_WIDTH)] for _ in range(WORLD_HEIGHT)]
        self.modified_blocks = {}
        if seed is None:
            self.seed = random.random() * 1000
        else:
            self.seed = seed
        self._generate()

    def _generate(self):
        """Procedural generation – Stardew Valley style rolling hills."""
        rng = random.Random(self.seed)
        for x in range(WORLD_WIDTH):
            # Gentler rolling hills
            h1 = math.sin(x * 0.05 + self.seed) * 8
            h2 = math.sin(x * 0.02 + self.seed * 0.7) * 15
            h3 = math.sin(x * 0.13 + self.seed * 1.3) * 3
            height = int(200 + h1 + h2 + h3)

            for y in range(WORLD_HEIGHT):
                if y < height:
                    self.grid[y][x] = B_AIR
                elif y == height:
                    # Surface layer: grass
                    self.grid[y][x] = B_GRASS
                elif y < height + 6:
                    self.grid[y][x] = B_DIRT
                elif y < height + 12:
                    # Mix of dirt and stone transition
                    if rng.random() < 0.4:
                        self.grid[y][x] = B_STONE
                    else:
                        self.grid[y][x] = B_DIRT
                else:
                    self.grid[y][x] = B_STONE

            # Surface decorations
            if self.grid[height][x] == B_GRASS and height > 5:
                r = rng.random()
                if r < 0.03:
                    # Trees with leaf canopy
                    self._build_tree(x, height, rng)
                elif r < 0.06:
                    self.grid[height - 1][x] = B_WHEAT
                elif r < 0.08:
                    self.grid[height - 1][x] = B_FLOWER_RED
                elif r < 0.10:
                    self.grid[height - 1][x] = B_FLOWER_YELLOW

    def _build_tree(self, x, base_y, rng=None):
        if rng is None:
            rng = random.Random()
        trunk_h = rng.randint(4, 6)
        # Trunk
        for i in range(1, trunk_h + 1):
            if base_y - i >= 0:
                self.grid[base_y - i][x] = B_WOOD
        # Leaf canopy (rounded)
        top_y = base_y - trunk_h
        for dy in range(-2, 2):
            for dx in range(-2, 3):
                lx, ly = x + dx, top_y + dy
                if 0 <= lx < WORLD_WIDTH and 0 <= ly < WORLD_HEIGHT:
                    if self.grid[ly][lx] == B_AIR:
                        dist = abs(dx) + abs(dy)
                        if dist <= 3 and not (dist == 3 and rng.random() < 0.4):
                            self.grid[ly][lx] = B_LEAF

    def get_block(self, x, y):
        if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
            return self.grid[y][x]
        return B_STONE # Out of bounds is solid

    def set_block(self, x, y, block_type):
        if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
            self.grid[y][x] = block_type
            self.modified_blocks[(x, y)] = block_type
            return True
        return False

    def get_modified_blocks_list(self):
        return [{"x": k[0], "y": k[1], "type": v} for k, v in self.modified_blocks.items()]
        
    def apply_modified_blocks(self, blocks_list):
        for b in blocks_list:
            self.set_block(b["x"], b["y"], b["type"])

# --- Crafting ---
CRAFTING_RECIPES = {
    T_PICKAXE: {I_WOOD: 1, I_STONE: 3},
    T_SHOVEL: {I_WOOD: 1, I_STONE: 1},
    T_AXE: {I_WOOD: 4}, # Hacha: 4 madera
    I_BREAD: {I_WHEAT: 3},
    I_CHEST: {I_WOOD: 4}  # Cofre: 4 madera
}

# --- Player Logic ---
class Player:
    def __init__(self, x=200, y=150):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.width = 0.8
        self.height = 1.8
        self.speed = 5.0
        self.jump_power = 8.0
        self.gravity = 15.0
        self.on_ground = False
        
        # Inventory: item_id -> amount
        self.inventory = {}
        self.selected_item = I_DIRT
        self.health = 10
        self.hunger = 10

    def add_item(self, item_id, amount=1):
        if item_id in self.inventory:
            self.inventory[item_id] += amount
        else:
            self.inventory[item_id] = amount

    def remove_item(self, item_id, amount=1):
        if item_id in self.inventory and self.inventory[item_id] >= amount:
            self.inventory[item_id] -= amount
            if self.inventory[item_id] == 0:
                del self.inventory[item_id]
            return True
        return False

    def can_craft(self, result_id):
        recipe = CRAFTING_RECIPES.get(result_id)
        if not recipe: return False
        for req_id, req_amt in recipe.items():
            if self.inventory.get(req_id, 0) < req_amt:
                return False
        return True

    def craft(self, result_id):
        if self.can_craft(result_id):
            recipe = CRAFTING_RECIPES[result_id]
            for req_id, req_amt in recipe.items():
                self.remove_item(req_id, req_amt)
            self.add_item(result_id, 1)
            return True
        return False

    def update(self, dt, world, input_dx, jump):
        # Apply inputs
        self.vx = input_dx * self.speed
        if jump and self.on_ground:
            self.vy = -self.jump_power
            self.on_ground = False
            
        # Apply gravity
        self.vy += self.gravity * dt
        
        # Move X
        self.x += self.vx * dt
        if self._check_collision(world):
            self.x -= self.vx * dt
            self.vx = 0
            
        # Move Y
        self.y += self.vy * dt
        self.on_ground = False
        if self._check_collision(world):
            self.y -= self.vy * dt
            if self.vy > 0:
                self.on_ground = True
            self.vy = 0

    def _check_collision(self, world):
        # Simplistic AABB collision against grid
        min_x = int(math.floor(self.x))
        max_x = int(math.floor(self.x + self.width))
        min_y = int(math.floor(self.y))
        max_y = int(math.floor(self.y + self.height))
        
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                block = world.get_block(x, y)
                if block not in NON_SOLID:
                    return True
        return False

    def interact_block(self, world, bx, by, action="break"):
        """Break or Place block if within reach."""
        dist = math.hypot(bx - (self.x + self.width/2), by - (self.y + self.height/2))
        if dist > 5.0:
            return False # Too far
            
        if action == "break":
            block = world.get_block(bx, by)
            if block != B_AIR:
                # Los cofres no se pueden romper con click izquierdo.
                # Deben quedarse siempre colocados en el suelo.
                if block == B_CHEST:
                    return False
                world.set_block(bx, by, B_AIR)
                # Map block -> item drop
                drop = block
                if block == B_GRASS:
                    drop = I_DIRT   # grass drops dirt
                elif block == B_LEAF:
                    # leaves sometimes drop nothing
                    if random.random() < 0.3:
                        return True  # broke but no drop
                    drop = I_WOOD
                elif block in (B_FLOWER_RED, B_FLOWER_YELLOW):
                    drop = I_WHEAT  # flowers drop wheat
                self.add_item(drop, 1)
                return True
                
        elif action == "place":
            # Can only place if empty
            cur = world.get_block(bx, by)
            if cur in NON_SOLID:
                if self.selected_item in (I_DIRT, I_STONE, I_WOOD, I_WHEAT, I_SAND):
                    if self.remove_item(self.selected_item, 1):
                        world.set_block(bx, by, self.selected_item)
                        return True
                elif self.selected_item == I_CHEST:
                    if self.remove_item(I_CHEST, 1):
                        world.set_block(bx, by, B_CHEST)
                        # El cofre se crea en main.py cuando se sincroniza
                        return True
        return False

    def eat(self):
        if self.remove_item(I_BREAD, 1) or self.remove_item(I_MEAT, 1):
            self.hunger = min(10, self.hunger + 3)
            self.health = min(10, self.health + 1)
            return True
        return False

    def serialize_inventory(self):
        # JSON requiere claves string, convertimos int->str explícitamente
        return {
            "inventory": {str(k): v for k, v in self.inventory.items()},
            "health": self.health,
            "hunger": self.hunger
        }
        
    def deserialize_inventory(self, data):
        # Convertir claves string de vuelta a int
        raw_inv = data.get("inventory", {})
        self.inventory = {int(k): v for k, v in raw_inv.items()}
        self.health = data.get("health", 10)
        self.hunger = data.get("hunger", 10)


# --- Chests (Cofres Privados) ---
class Chest:
    """Cofre privado que pertenece a un jugador. Su contenido está encriptado con su clave pública."""
    
    def __init__(self, chest_id, owner_peer_id, position=(0, 0)):
        """
        chest_id: identificador único del cofre (ej: uuid o hash)
        owner_peer_id: peer_id del propietario (su clave pública se usará para encriptar)
        position: (x, y) coordenadas del cofre en el mundo
        """
        self.chest_id = chest_id
        self.owner_peer_id = owner_peer_id
        self.inventory = {}  # item_id -> amount
        self.position = position  # (world_x, world_y)
    
    def add_item(self, item_id, amount=1):
        """Agrega un item al cofre."""
        if item_id in self.inventory:
            self.inventory[item_id] += amount
        else:
            self.inventory[item_id] = amount
    
    def remove_item(self, item_id, amount=1):
        """Remueve un item del cofre si hay suficientes."""
        if item_id in self.inventory and self.inventory[item_id] >= amount:
            self.inventory[item_id] -= amount
            if self.inventory[item_id] == 0:
                del self.inventory[item_id]
            return True
        return False
    
    def serialize(self):
        """Serializa el inventario del cofre para guardar encriptado."""
        return {
            "chest_id": self.chest_id,
            "owner_peer_id": self.owner_peer_id,
            "position": [self.position[0], self.position[1]],
            "inventory": {str(k): v for k, v in self.inventory.items()}
        }
    
    @staticmethod
    def deserialize(data):
        """Deserializa los datos del cofre."""
        pos = data.get("position", [0, 0])
        if not isinstance(pos, (list, tuple)) or len(pos) != 2:
            pos = [0, 0]
        chest = Chest(data.get("chest_id"), data.get("owner_peer_id"), position=(int(pos[0]), int(pos[1])))
        raw_inv = data.get("inventory", {})
        chest.inventory = {int(k): v for k, v in raw_inv.items()}
        return chest
