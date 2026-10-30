---
name: s3p-illumination-module
description: >-
  Comprehensive reference for the S3P Illumination module (brightness, color, backlight
  dimming, adaptive illumination) for creating targeted unit and integration tests.
  Use when: writing test cases for brightness/color control or fade effects; testing
  adaptive illumination driven by ambient light; working with DIDs 0xFD70-0xFD73.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P Illumination Module Skill

## Overview
This skill provides comprehensive information about the S3P Illumination module for creating targeted unit and integration tests. The Illumination module is responsible for controlling display brightness, color, and illumination patterns in the S3P SITS system.

## Module Purpose
The Illumination module manages:
- **Brightness control**: Adjusting display brightness levels
- **Color control**: Managing display color output
- **Backlight dimming**: LED driver control
- **Adaptive illumination**: Automatic brightness adjustment based on ambient light
- **Illumination patterns**: Special visual effects and patterns
- **Fade effects**: Smooth transitions between brightness levels

## Component Architecture

### External Interfaces
```
Illumination Module
├── LED Driver Interface
│   ├── PWM signal for brightness
│   ├── Current monitoring
│   ├── Temperature feedback
│   └── Fault detection
│
├── Color Control Interface
│   ├── RGB LED control (if available)
│   ├── Color mixing
│   └── Color temperature adjustment
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD70: Current Brightness
│   ├── DID 0xFD71: Color Settings
│   ├── DID 0xFD72: Illumination Mode
│   └── DID 0xFD73: LED Status
│
├── Signal Interface
│   ├── Brightness request signals
│   ├── Mode control signals
│   └── Illumination effect signals
│
└── Dependent Modules
    ├── Ambient Sense (for adaptive control)
    ├── Power Control (power monitoring)
    └── App Mode Mng (mode-specific settings)
```

### Brightness Levels
```
Level 0: Off
- Display dark
- LED backlight off
- Minimal power consumption

Level 1-25: Minimum
- Lowest visible brightness
- Used in dark environments
- Power efficient

Level 26-75: Medium
- Standard operating brightness
- Comfortable for most environments
- Balanced power consumption

Level 76-100: Maximum
- Full brightness
- Used in bright sunlight
- High power consumption
```

## Key Data Structures

### Current Brightness DID (0xFD70)
```
Field                   Range       Description
CurrentBrightness      0-100       Current brightness percentage
TargetBrightness       0-100       Requested brightness
BrightnessMode         0-3         0=Manual, 1=Auto, 2=Adaptive, 3=Special
FadeTimeMs             0-65535     Fade time to target (ms)
```

### Color Settings DID (0xFD71)
```
Field                   Range       Description
RedChannel             0-255       Red intensity
GreenChannel           0-255       Green intensity
BlueChannel            0-255       Blue intensity
ColorTemperatureK      2000-10000  Color temperature in Kelvin
```

### Illumination Mode DID (0xFD72)
```
Field                   Range       Description
ActiveMode             0-5         Current illumination mode
AvailableModes         (bitmap)    Available mode bitmap
EffectSpeed            0-100       Effect playback speed (%)
EffectIntensity        0-100       Effect intensity level
```

### LED Status DID (0xFD73)
```
Field                   Range       Description
LEDHealthStatus        0-3         LED operational status
LEDCurrentDraw         0-65535     Current consumption (mA)
LEDTemperature         0-127       LED die temperature (°C)
LEDErrorCode           0x00-0xFF   Any LED-specific errors
```

## Test Scenarios by Feature

### Feature 1: Brightness Control
**Scenario: Manual Brightness Adjustment**
```
Test Brightness Levels:
- Level 0: Off
- Level 25: Minimum visible
- Level 50: Medium/Normal
- Level 75: High
- Level 100: Maximum

Test Cases Needed:
1. Set brightness to each level
2. Verify actual brightness matches
3. Verify LED current appropriate
4. Verify power consumption scales
5. Boundary conditions (0, 100)
```

**Scenario: Adaptive Brightness**
```
Ambient Light Integration:
- Dark (10 lux) → 25% brightness
- Dim (100 lux) → 50% brightness
- Normal (500 lux) → 75% brightness
- Bright (5000 lux) → 100% brightness

Test Cases Needed:
1. Receive ambient light level
2. Calculate appropriate brightness
3. Adjust brightness automatically
4. Prevent oscillation at threshold
5. Hysteresis in transitions
```

### Feature 2: Brightness Fade Effects
**Scenario: Smooth Transitions**
```
Fade Times:
- Instant: 0ms
- Fast: 100ms
- Normal: 500ms
- Slow: 1000ms
- Very Slow: 2000ms

Test Cases Needed:
1. Fade from 0% to 100% (slow)
2. Fade from 100% to 0% (fade out)
3. Rapid brightness changes
4. Linear vs. non-linear fade curves
5. Fade interruption handling
```

### Feature 3: Color Control
**Scenario: RGB Color Output (if available)**
```
Color Modes:
- White: R=255, G=255, B=255
- Red: R=255, G=0, B=0
- Green: R=0, G=255, B=0
- Blue: R=0, G=0, B=255
- Custom: User-defined RGB values

Test Cases Needed:
1. Set primary colors
2. Mix custom colors
3. Color accuracy verification
4. Color uniformity across display
5. Color rendering in different modes
```

**Scenario: Color Temperature Adjustment**
```
Temperature Transitions:
- Warm (2700K): Evening mode
- Neutral (4000K): Standard mode
- Cool (6500K): Daytime mode

Test Cases Needed:
1. Temperature adjustment
2. Smooth transitions
3. Accuracy of temperature adjustment
4. Power consumption impact
5. Interaction with app mode
```

### Feature 4: Illumination Modes
**Scenario: Mode-Specific Illumination**
```
Illumination Modes:
- Mode 0: Normal (constant brightness)
- Mode 1: Animated (pulse effect)
- Mode 2: Breathing (slow fade in/out)
- Mode 3: Alert (rapid flash)
- Mode 4: Notification (slow blink)
- Mode 5: Custom pattern

Test Cases Needed:
1. Activate each mode
2. Verify pattern generation
3. Verify timing accuracy
4. Mode transition handling
5. Power consumption per mode
```

### Feature 5: LED Health Monitoring
**Scenario: LED Status and Fault Detection**
```
Monitoring:
- LED current draw
- LED temperature
- LED aging/degradation
- LED failure detection

Test Cases Needed:
1. Normal operation current
2. Over-current detection
3. Temperature monitoring
4. Thermal shutdown at limit
5. LED failure detection
6. Graceful degradation
```

### Feature 6: Power-Efficient Operations
**Scenario: Power Consumption Optimization**
```
Power Modes:
- Full brightness: 5W max
- Standard: 3W typical
- Minimum: 0.5W
- Off: < 10mW

Test Cases Needed:
1. Power consumption at each level
2. Verification of efficiency
3. PWM frequency validation
4. Thermal management
5. Battery life impact
```

## Mock Requirements

### LED Driver Mock
```cpp
class MockLEDDriver {
public:
    MOCK_METHOD(void, SetBrightness, (uint8_t percent));
    MOCK_METHOD(uint8_t, GetBrightness, ());
    MOCK_METHOD(void, SetColor, (uint8_t r, uint8_t g, uint8_t b));
    MOCK_METHOD(uint16_t, GetCurrentDraw, ());
    MOCK_METHOD(void, EnableFade, (uint16_t time_ms));
};
```

### PWM Controller Mock
```cpp
class MockPWMController {
public:
    MOCK_METHOD(void, SetDutyCycle, (uint8_t percent));
    MOCK_METHOD(uint8_t, GetDutyCycle, ());
    MOCK_METHOD(void, SetFrequency, (uint16_t hz));
    MOCK_METHOD(bool, IsEnabled, ());
};
```

### Temperature Sensor Mock
```cpp
class MockTemperatureSensor {
public:
    MOCK_METHOD(int8_t, ReadTemperature, ());
    MOCK_METHOD(bool, IsOverTemp, ());
    MOCK_METHOD(bool, IsNormal, ());
};
```

## Key Test Data

### Brightness Test Values
```
BOUNDARY VALUES:
- Minimum: 0 (off)
- Just Above Min: 1
- Low: 25
- Medium: 50
- High: 75
- Maximum: 100

EQUIVALENCE PARTITIONS:
- Off: 0
- Minimal: 1-10
- Low: 11-25
- Medium: 26-75
- High: 76-99
- Maximum: 100

FADE TIMES (ms):
- Instant: 0
- Fast: 100
- Normal: 500
- Slow: 1000
- Very Slow: 2000
```

### Color Test Values
```
RGB VALUES:
- Black: (0, 0, 0)
- White: (255, 255, 255)
- Red: (255, 0, 0)
- Green: (0, 255, 0)
- Blue: (0, 0, 255)
- Yellow: (255, 255, 0)
- Cyan: (0, 255, 255)
- Magenta: (255, 0, 255)

COLOR TEMPERATURE (K):
- Warm: 2700, 3000
- Neutral: 4000, 5000
- Cool: 6500, 7000
```

## Error Codes
```
0x00: No error
0x01: LED not responding
0x02: Over-current detected
0x03: Over-temperature detected
0x04: LED driver communication error
0x05: PWM controller error
0x06: Brightness out of range
0x07: Invalid color values
0x08: Thermal throttling active
0x09: LED aging detected
0xFF: Unknown LED error
```

## Common Test Patterns

### Pattern 1: Brightness Level Test
```robot
Test Case - Set Brightness To [Level] Percent
    [Tags]    brightness    illumination
    Set Brightness    ${level}
    Wait For Stabilization    500ms
    Read Brightness Level    ${measured}
    Verify Brightness Correct    expected=${level}
    Verify LED Current Appropriate    for_brightness=${level}
    Verify No LED Errors
```

### Pattern 2: Fade Transition Test
```robot
Test Case - Fade From [FromLevel] To [ToLevel] In [TimeMs]
    [Tags]    fade    brightness
    Set Brightness    ${from_level}
    Fade Brightness To    ${to_level}    time=${time_ms}
    Monitor Fade Progression    at_intervals=100ms
    Verify Final Brightness    ${to_level}
    Verify Fade Time Accurate    ±50ms
```

### Pattern 3: Color Test
```robot
Test Case - Set Color To [ColorName] (R=[R] G=[G] B=[B])
    [Tags]    color    illumination
    Set Color    r=${r}    g=${g}    b=${b}
    Wait For Color Applied
    Read Color Output
    Verify Color Accuracy    ±10%
```

## GTF Unit Test Structure

```cpp
TEST_F(IlluminationFixture, BrightnessControlBasic)
{
    EXPECT_CALL(led_driver, SetBrightness(50)).Times(1);
    EXPECT_CALL(led_driver, GetBrightness).WillOnce(Return(50));
    
    illumination.SetBrightness(50);
    uint8_t brightness = illumination.GetBrightness();
    
    EXPECT_EQ(brightness, 50);
}

TEST_F(IlluminationFixture, AdaptiveBrightnessFromAmbientLight)
{
    EXPECT_CALL(ambient_mock, GetAmbientLight)
        .WillOnce(Return(500));  // Office light
    
    illumination.UpdateAdaptiveBrightness();
    uint8_t expected_brightness = 75;
    
    EXPECT_GE(illumination.GetBrightness(), expected_brightness - 5);
    EXPECT_LE(illumination.GetBrightness(), expected_brightness + 5);
}

TEST_F(IlluminationFixture, BrightnessFadeWithCorrectTiming)
{
    EXPECT_CALL(led_driver, EnableFade(500)).Times(1);
    EXPECT_CALL(led_driver, SetBrightness(100)).Times(1);
    
    illumination.FadeBrightness(100, 500);  // Fade to 100% in 500ms
    
    EXPECT_EQ(illumination.GetBrightness(), 100);
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P Illumination Module
Resource       ../../resources/S3P_Illumination/s3p_illumination_pf.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
Set Brightness To 50 Percent
    [Documentation]    Tests manual brightness adjustment
    [Tags]    integration    brightness    illumination
    Set Brightness    50
    Wait For LED Stabilization    500ms
    Read Display Brightness
    Verify Brightness Level    50±5%
    Verify LED Current    1.5A±0.1A
    Verify No LED Errors

Adaptive Brightness From Ambient Light
    [Documentation]    Tests automatic brightness adjustment
    [Tags]    integration    adaptive    ambient
    Set Ambient Light    500lux
    Wait For Adaptation    2s
    Read Display Brightness
    Verify Brightness Adapted    65-85%
    Verify Smooth Transition

Brightness Fade 0 To 100 In 1 Second
    [Documentation]    Tests fade effect timing and smoothness
    [Tags]    integration    fade    brightness
    Set Brightness    0
    Fade Brightness To    100    time=1000ms
    Monitor Fade Progression    at=100ms_intervals
    Verify Final Brightness    100
    Verify Fade Duration    1000±50ms
    Verify Smooth Progression

Color Setting White
    [Documentation]    Tests RGB color output
    [Tags]    integration    color    rgb
    Set Color    r=255    g=255    b=255
    Wait For Color Applied    500ms
    Verify Color Output    White±5%
    Verify Color Uniformity
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85%
- **Branch Coverage**: ≥80%
- **Path Coverage**: ≥70%

### Functional Coverage
- ✓ Manual brightness control (0-100%)
- ✓ Adaptive brightness from ambient light
- ✓ Fade effects (instant, fast, slow)
- ✓ Color control (RGB if available)
- ✓ Color temperature adjustment
- ✓ Illumination modes/patterns
- ✓ LED health monitoring
- ✓ Error detection and handling

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For illumination constants
- `s3p-ambientsense-module` - For ambient light integration
- `test-strategy-planning` - For test planning

## Module-Specific Files

Location: `resources/S3P_Illumination/`
- `s3p_illumination_pf.robot` - Platform-specific keywords
- `s3p_illumination_prj.robot` - Project-specific utilities

## Troubleshooting Common Issues

### Issue: Brightness Not Responding
- Verify LED driver communication
- Check PWM signal output
- Validate brightness value range
- Check power supply to LEDs

### Issue: Color Accuracy Poor
- Verify RGB calibration
- Check color mixing matrix
- Validate sensor readings
- Check for thermal drift

### Issue: Fade Not Smooth
- Verify PWM frequency adequate
- Check fade algorithm
- Validate timing precision
- Monitor for power glitches
