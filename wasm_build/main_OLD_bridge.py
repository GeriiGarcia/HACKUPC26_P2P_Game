import asyncio
import pygame
import sys

async def main():
    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("WASM Bridge Test")
    
    font = pygame.font.SysFont(None, 36)
    clock = pygame.time.Clock()
    
    # Intentar detectar el bridge de JS
    try:
        import platform
        if sys.platform == 'emscripten':
            from platform import window
            bridge = window.p2pBridge
            print(f"[PYTHON] Bridge detectado: {bridge.myPeerId}")
        else:
            bridge = None
            print("[PYTHON] No estamos en WASM, bridge no disponible")
    except Exception as e:
        print(f"[PYTHON] Error detectando bridge: {e}")
        bridge = None

    running = True
    while running:
        screen.fill((50, 50, 50))
        
        text = "WASM P2P Bridge Test"
        if bridge:
            text += f" | ID: {bridge.myPeerId}"
        
        img = font.render(text, True, (255, 255, 255))
        screen.blit(img, (20, 20))
        
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        pygame.display.flip()
        # CRITICAL: await asyncio.sleep(0) for Pygbag
        await asyncio.sleep(0)

if __name__ == "__main__":
    asyncio.run(main())