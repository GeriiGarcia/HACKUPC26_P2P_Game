import time
import random
import math

# Estados de la mascota
STATE_IDLE = 0
STATE_EATING = 1
STATE_SLEEPING = 2
STATE_PLAYING = 3
STATE_DIRTY = 4

class Pet:
    def __init__(self, owner_id):
        self.owner_id = owner_id
        self.x = random.randint(100, 600)
        self.y = 400 # Suelo de la habitación
        self.vx = 0
        
        # Stats (0 a 100)
        self.hunger = 100
        self.energy = 100
        self.fun = 100
        self.cleanliness = 100
        
        self.state = STATE_IDLE
        self.state_timer = 0
        self.target_x = self.x

    def update(self, dt):
        """Actualiza el estado de la mascota y decae sus stats con el tiempo."""
        # Decaimiento pasivo
        if self.state != STATE_SLEEPING:
            self.energy -= 0.5 * dt
        self.hunger -= 1.0 * dt
        self.fun -= 0.8 * dt
        self.cleanliness -= 0.3 * dt
        
        # Limitar stats
        self.hunger = max(0, min(100, self.hunger))
        self.energy = max(0, min(100, self.energy))
        self.fun = max(0, min(100, self.fun))
        self.cleanliness = max(0, min(100, self.cleanliness))

        # Lógica de estados
        if self.state_timer > 0:
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.state = STATE_IDLE
                self.state_timer = 0

        # Movimiento autónomo básico (deambular)
        if self.state == STATE_IDLE:
            if abs(self.target_x - self.x) < 5:
                # Elegir nuevo objetivo si estamos inactivos
                if random.random() < 0.02:  # 2% chance per frame aprox si dt es 1/60
                    self.target_x = random.randint(100, 600)
            else:
                # Moverse hacia el objetivo
                self.vx = 40 if self.target_x > self.x else -40
                self.x += self.vx * dt
                
        # Si está durmiendo, no se mueve y recupera energía
        elif self.state == STATE_SLEEPING:
            self.energy += 5.0 * dt
            if self.energy >= 100:
                self.state = STATE_IDLE
                
        # Si la limpieza es 0, forzar estado sucio a menos que hagamos otra accion
        if self.cleanliness <= 0 and self.state == STATE_IDLE:
            self.state = STATE_DIRTY
            
    def feed(self):
        if self.state not in (STATE_SLEEPING,):
            self.hunger = min(100, self.hunger + 30)
            self.state = STATE_EATING
            self.state_timer = 2.0  # Come durante 2 segundos
            return True
        return False

    def play(self):
        if self.state not in (STATE_SLEEPING,) and self.energy > 10:
            self.fun = min(100, self.fun + 40)
            self.energy -= 10
            self.cleanliness -= 5
            self.state = STATE_PLAYING
            self.state_timer = 3.0
            return True
        return False

    def sleep(self):
        if self.state != STATE_SLEEPING:
            self.state = STATE_SLEEPING
            self.state_timer = 10.0 # Duerme 10 segundos mínimo o hasta llenar energía
            return True
        return False
        
    def clean(self):
        self.cleanliness = 100
        self.state = STATE_IDLE
        return True

    def serialize_state(self):
        return {
            "owner_id": self.owner_id,
            "x": self.x,
            "y": self.y,
            "hunger": self.hunger,
            "energy": self.energy,
            "fun": self.fun,
            "cleanliness": self.cleanliness,
            "state": self.state,
            "state_timer": self.state_timer
        }

    def deserialize_state(self, data):
        self.x = data.get("x", self.x)
        self.y = data.get("y", self.y)
        self.hunger = data.get("hunger", self.hunger)
        self.energy = data.get("energy", self.energy)
        self.fun = data.get("fun", self.fun)
        self.cleanliness = data.get("cleanliness", self.cleanliness)
        self.state = data.get("state", self.state)
        self.state_timer = data.get("state_timer", self.state_timer)
