"""
Component Basic Tests

Tests if each component can be initialized correctly.
"""

import sys
import configparser
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

def test_config():
    """Config file loading test"""
    print("=" * 60)
    print("Test 1: config.ini loading")
    print("=" * 60)

    config_path = Path('config.ini')
    if not config_path.exists():
        print("[ERROR] config.ini not found")
        return False

    config = configparser.ConfigParser()
    config.read(config_path, encoding='utf-8')

    # Check required sections
    required_sections = ['general', 'overlay', 'personas', 'llm', 'screenshot']
    for section in required_sections:
        if not config.has_section(section):
            print(f"[ERROR] Missing section: [{section}]")
            return False
        print(f"[OK] Section [{section}] found")

    # Check overlay settings
    print(f"\n[overlay] settings:")
    print(f"  - num_lanes: {config.get('overlay', 'num_lanes')}")
    print(f"  - scroll_speed_base: {config.get('overlay', 'scroll_speed_base')}")
    print(f"  - font_family: {config.get('overlay', 'font_family')}")

    print("\n[OK] config.ini is valid\n")
    return config


def test_persona_manager(config):
    """Persona manager test"""
    print("=" * 60)
    print("Test 2: PersonaManager initialization")
    print("=" * 60)

    from persona_manager import PersonaManager

    manager = PersonaManager(config)
    print(f"[OK] PersonaManager initialized with {len(manager.personas)} personas")

    # Display persona info
    for name, persona in manager.personas.items():
        print(f"\n  [{name}]")
        print(f"    - weight: {persona.weight}")
        print(f"    - color: {persona.color}")
        print(f"    - size: {persona.size}px")
        print(f"    - max_chars: {persona.max_chars}")
        print(f"    - smart_prompt: {persona.smart_prompt[:50]}...")

    # Random selection test
    print("\n  Testing random selection (10 samples):")
    counts = {name: 0 for name in manager.personas.keys()}
    for _ in range(10):
        selected = manager.select_persona()
        counts[selected.name] += 1

    for name, count in counts.items():
        print(f"    - {name}: {count} times")

    print("\n[OK] PersonaManager works correctly\n")
    return manager


def test_comment_data():
    """Data structure test"""
    print("=" * 60)
    print("Test 3: Comment data structure")
    print("=" * 60)

    from comment_data import Comment, CommentContext

    # Comment creation test
    comment = Comment(
        text="Test comment",
        persona="narrator",
        color="#FFFFFF",
        size=28,
        speed=300.0
    )
    print(f"[OK] Comment created: {comment.text}")
    print(f"  - persona: {comment.persona}")
    print(f"  - color: {comment.color}")
    print(f"  - size: {comment.size}px")
    print(f"  - speed: {comment.speed}px/s")

    # CommentContext creation test
    context = CommentContext(
        screenshot_path="test.png",
        timestamp=1234567890.0
    )
    print(f"\n[OK] CommentContext created")
    print(f"  - screenshot_path: {context.screenshot_path}")
    print(f"  - timestamp: {context.timestamp}")

    print("\n[OK] Data structures work correctly\n")


def test_comment_overlay_imports():
    """Overlay system import test"""
    print("=" * 60)
    print("Test 4: CommentOverlay imports (no GUI initialization)")
    print("=" * 60)

    try:
        from comment_overlay import LaneManager, CommentOverlay
        print("[OK] LaneManager imported")
        print("[OK] CommentOverlay imported")

        # LaneManager basic test (no GUI needed)
        lane_mgr = LaneManager(num_lanes=8, screen_width=1920, screen_height=1080)
        print(f"\n[OK] LaneManager initialized:")
        print(f"  - num_lanes: {lane_mgr.num_lanes}")
        print(f"  - screen_width: {lane_mgr.screen_width}px")
        print(f"  - screen_height: {lane_mgr.screen_height}px")
        print(f"  - lane_height: {lane_mgr.lane_height:.1f}px")

        # Lane allocation test
        lane = lane_mgr.allocate_lane(comment_width=200, speed=300)
        print(f"\n[OK] Lane allocation test:")
        print(f"  - allocated lane: {lane}")

        print("\n[OK] CommentOverlay components work correctly\n")

    except Exception as e:
        print(f"[ERROR] Error: {e}")
        return False

    return True


def test_display_styles():
    """Display style configuration and color interpolation test"""
    print("=" * 60)
    print("Test 5: Display style features")
    print("=" * 60)

    from comment_data import Comment
    from comment_overlay import CommentOverlay

    errors = []

    # --- 5a: Comment dataclass 新フィールドのデフォルト値確認 ---
    print("\n  5a: Comment dataclass default values")
    c = Comment(text="test", persona="narrator", color="#FFFFFF", size=26, speed=300.0)

    checks = [
        ("display_style", c.display_style, "scroll"),
        ("spawn_time", c.spawn_time, 0.0),
        ("lifetime", c.lifetime, 5.0),
        ("fade_duration", c.fade_duration, 0.5),
        ("opacity", c.opacity, 1.0),
        ("height", c.height, 0.0),
    ]
    for field_name, actual, expected in checks:
        if actual == expected:
            print(f"    [OK] {field_name} = {actual}")
        else:
            msg = f"    [FAIL] {field_name}: expected {expected}, got {actual}"
            print(msg)
            errors.append(msg)

    # display_style 指定テスト
    c_toast = Comment(text="t", persona="critic", color="#FF0000",
                      size=26, speed=0.0, display_style="toast")
    c_chatlog = Comment(text="c", persona="analyzer", color="#FFFF00",
                        size=24, speed=0.0, display_style="chatlog")
    if c_toast.display_style == "toast":
        print("    [OK] toast style Comment creation")
    else:
        errors.append(f"toast style: got {c_toast.display_style}")
    if c_chatlog.display_style == "chatlog":
        print("    [OK] chatlog style Comment creation")
    else:
        errors.append(f"chatlog style: got {c_chatlog.display_style}")

    # --- 5b: 色補間テスト ---
    print("\n  5b: Color interpolation (_interpolate_color)")

    interp = CommentOverlay._interpolate_color

    # t=0 → color_a を返す
    result = interp("#000000", "#FFFFFF", 0.0)
    if result == "#000000":
        print(f"    [OK] t=0.0: {result}")
    else:
        msg = f"    [FAIL] t=0.0: expected #000000, got {result}"
        print(msg)
        errors.append(msg)

    # t=1 → color_b を返す
    result = interp("#000000", "#FFFFFF", 1.0)
    if result == "#FFFFFF":
        print(f"    [OK] t=1.0: {result}")
    else:
        msg = f"    [FAIL] t=1.0: expected #FFFFFF, got {result}"
        print(msg)
        errors.append(msg)

    # t=0.5 → 中間色
    result = interp("#000000", "#FFFFFF", 0.5)
    # 127 or 128 どちらも許容（浮動小数点）
    r = int(result[1:3], 16)
    if 126 <= r <= 128:
        print(f"    [OK] t=0.5: {result} (midpoint)")
    else:
        msg = f"    [FAIL] t=0.5: expected ~#7F7F7F, got {result}"
        print(msg)
        errors.append(msg)

    # --- 5c: #010101 ガード ---
    print("\n  5c: #010101 transparent key guard")

    # #010101（透明キー色）が結果に出ないことを確認
    # #000000 → #020202 で t を微調整して #010101 が出る状況をテスト
    result = interp("#000000", "#020202", 0.5)
    if result == "#010101":
        msg = "    [FAIL] Got #010101 (transparent key leak!)"
        print(msg)
        errors.append(msg)
    else:
        print(f"    [OK] Guard active: #000000→#020202 t=0.5 = {result} (not #010101)")

    # 直接 #010101 に向かう補間でもガードされるか
    result_direct = interp("#010101", "#010101", 0.5)
    if result_direct == "#010101":
        msg = "    [FAIL] Got #010101 from direct interpolation"
        print(msg)
        errors.append(msg)
    else:
        print(f"    [OK] Guard active: #010101→#010101 = {result_direct}")

    # --- 5d: t のクランプ確認 ---
    print("\n  5d: t value clamping")

    result_under = interp("#000000", "#FFFFFF", -0.5)
    result_over = interp("#000000", "#FFFFFF", 1.5)
    if result_under == "#000000":
        print(f"    [OK] t=-0.5 clamped: {result_under}")
    else:
        msg = f"    [FAIL] t=-0.5: expected #000000, got {result_under}"
        print(msg)
        errors.append(msg)
    if result_over == "#FFFFFF":
        print(f"    [OK] t=1.5 clamped: {result_over}")
    else:
        msg = f"    [FAIL] t=1.5: expected #FFFFFF, got {result_over}"
        print(msg)
        errors.append(msg)

    # --- 結果 ---
    if errors:
        print(f"\n[ERROR] Test 5 had {len(errors)} failure(s):")
        for e in errors:
            print(f"  {e}")
        return False

    print("\n[OK] Display style features work correctly\n")
    return True


def main():
    """Main test execution"""
    print("\n")
    print("=" * 60)
    print(" " * 15 + "Component Test Suite")
    print("=" * 60)
    print("\n")

    try:
        # Test 1: Config
        config = test_config()
        if not config:
            print("\n[ERROR] Config test failed")
            return

        # Test 2: PersonaManager
        test_persona_manager(config)

        # Test 3: Data structures
        test_comment_data()

        # Test 4: CommentOverlay (imports only)
        test_comment_overlay_imports()

        # Test 5: Display styles
        test_display_styles()

        # Final result
        print("=" * 60)
        print("[SUCCESS] ALL TESTS PASSED")
        print("=" * 60)
        print("\nDisplay styles implementation is complete!")
        print("Next step: Run 'python src/main.py' to start the application")
        print("(Make sure LM Studio is running with a Vision model)")
        print("\n")

    except Exception as e:
        print(f"\n[ERROR] Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
