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

BLOCK_NAMES = {
    B_AIR: "Aire",
    B_DIRT: "Tierra",
    B_STONE: "Piedra",
    B_WOOD: "Madera",
    B_WHEAT: "Trigo"
}

# Items
I_DIRT = 1
I_STONE = 2
I_WOOD = 3
I_WHEAT = 4
I_BREAD = 5
I_MEAT = 6
T_PICKAXE = 10
T_SHOVEL = 11
T_AXE = 12

ITEM_NAMES = {
    I_DIRT: "Bloque de Tierra",
    I_STONE: "Bloque de Piedra",
    I_WOOD: "Bloque de Madera",
    I_WHEAT: "Trigo",
    I_BREAD: "Pan",
    I_MEAT: "Carne",
    T_PICKAXE: "Pico",
    T_SHOVEL: "Pala",
    T_AXE: "Hacha",
}

# --- World Logic ---
class World:
    def __init__(self, seed=None):
        self.grid = [[B_AIR for _ in range(WORLD_WIDTH)] for _ in range(WORLD_HEIGHT)]
        if seed is None:
            self.seed = random.random() * 1000
        else:
            self.seed = seed
        self._generate()

    def _generate(self):
        """Procedural generation using simple noise/sine waves."""
        for x in range(WORLD_WIDTH):
            # Altura del terreno base (entre 180 y 220)
            height = int(200 + math.sin(x * 0.1 + self.seed) * 10 + math.sin(x * 0.03 + self.seed) * 20)
            
            for y in range(WORLD_HEIGHT):
                if y < height:
                    self.grid[y][x] = B_AIR
                elif y == height:
                    self.grid[y][x] = B_DIRT
                    # Random wheat on top
                    if random.random() < 0.1 and y > 0:
                        self.grid[y-1][x] = B_WHEAT
                    # Trees
                    elif random.random() < 0.05 and y > 4:
                        self._build_tree(x, y)
                elif y < height + 10:
                    if self.grid[y][x] == B_AIR: # No sobreescribir madera
                        self.grid[y][x] = B_DIRT
                else:
                    if self.grid[y][x] == B_AIR:
                        self.grid[y][x] = B_STONE

    def _build_tree(self, x, base_y):
        height = random.randint(3, 5)
        for i in range(1, height + 1):
            if base_y - i >= 0:
                self.grid[base_y - i][x] = B_WOOD

    def get_block(self, x, y):
        if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
            return self.grid[y][x]
        return B_STONE # Out of bounds is solid

    def set_block(self, x, y, block_type):
        if 0 <= x < WORLD_WIDTH and 0 <= y < WORLD_HEIGHT:
            self.grid[y][x] = block_type
            return True
        return False

# --- Crafting ---
CRAFTING_RECIPES = {
    T_PICKAXE: {I_WOOD: 1, I_STONE: 3},
    T_SHOVEL: {I_WOOD: 1, I_STONE: 1},
    T_AXE: {I_WOOD: 4}, # Hacha: 1 madera + 3 madera = 4 madera
    I_BREAD: {I_WHEAT: 3}
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
                if world.get_block(x, y) != B_AIR and world.get_block(x, y) != B_WHEAT:
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
                world.set_block(bx, by, B_AIR)
                # Map block ID to item ID (1-to-1 for now)
                self.add_item(block, 1)
                return True
                
        elif action == "place":
            # Can only place if empty
            if world.get_block(bx, by) == B_AIR or world.get_block(bx, by) == B_WHEAT:
                if self.selected_item in (I_DIRT, I_STONE, I_WOOD, I_WHEAT):
                    if self.remove_item(self.selected_item, 1):
                        world.set_block(bx, by, self.selected_item)
                        return True
        return False

    def eat(self):
        if self.remove_item(I_BREAD, 1) or self.remove_item(I_MEAT, 1):
            self.hunger = min(10, self.hunger + 3)
            self.health = min(10, self.health + 1)
            return True
        return False

    def serialize_inventory(self):
        return {
            "inventory": self.inventory,
            "health": self.health,
            "hunger": self.hunger
        }
        
    def deserialize_inventory(self, data):
        self.inventory = data.get("inventory", {})
        self.health = data.get("health", 10)
        self.hunger = data.get("hunger", 10)
