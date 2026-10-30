---
name: s3p-ambientsense-module
description: >-
  Comprehensive reference for the S3P Ambient Sense module (light/color/environmental
  sensing) for creating targeted unit and integration tests. Use when: writing test
  cases for ambient light or color temperature sensing; testing sensor calibration,
  drift compensation, or dawn/dusk threshold detection; working with DIDs 0xFD60-0xFD63.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P Ambient Sense Module Skill

## Overview
This skill provides comprehensive information about the S3P Ambient Sense module for creating targeted unit and integration tests. The Ambient Sense module is responsible for detecting and monitoring ambient conditions such as light intensity, color temperature, and environmental data for the S3P SITS system.

## Module Purpose
The Ambient Sense module manages:
- **Light detection**: Ambient light intensity measurement
- **Color temperature**: Sensing color temperature of ambient light
- **Environmental monitoring**: Temperature, humidity if available
- **Sensor calibration**: Sensor drift and temperature compensation
- **Data filtering**: Noise reduction and averaging
- **Threshold detection**: Dawn/dusk and brightness thresholds

## Component Architecture

### External Interfaces
```
Ambient Sense Module
├── Light Sensor Interface
│   ├── Ambient light sensor (ALS)
│   ├── I2C/Analog interface
│   ├── Calibration data
│   └── Gain settings
│
├── Color Temperature Sensor
│   ├── RGB or color sensor
│   ├── Color compensation
│   └── Temperature calculation
│
├── Environmental Sensors (Optional)
│   ├── Temperature sensor
│   ├── Humidity sensor
│   └── Barometric pressure
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD60: Ambient Light Level
│   ├── DID 0xFD61: Color Temperature
│   ├── DID 0xFD62: Sensor Status
│   └── DID 0xFD63: Environmental Data
│
└── Signal Interface
    ├── Light level signals
    ├── Day/Night mode signals
    └── Illumination control signals
```

### Sensor Measurement Ranges

**Ambient Light Level (Lux)**
```
- Starlight: 0.001 lux
- Moonlight: 0.01 lux
- Twilight: 0.1 lux
- Indoor (dim): 50 lux
- Indoor (office): 300-500 lux
- Outdoor (cloudy): 1,000-5,000 lux
- Outdoor (sunny): 10,000-50,000 lux
- Direct sunlight: 100,000+ lux
```

**Color Temperature (Kelvin)**
```
- Moonlight: 4,100K
- Fluorescent light: 4,000-5,000K
- Daylight: 5,500-6,500K
- Incandescent: 2,700-3,000K
- Evening: 2,000-3,000K
```

## Key Data Structures

### Ambient Light Level DID (0xFD60)
```
Field                   Range           Description
AmbientLightLux        0-65535         Measured light level (lux)
FilteredLightLux       0-65535         Filtered/averaged value
LightSensorStatus      0-3             0=OK, 1=Warn, 2=Error, 3=Not Ready
DayNightMode           0-2             0=Day, 1=Twilight, 2=Night
LightChangeRate        0-65535         Rate of light change
```

### Color Temperature DID (0xFD61)
```
Field                   Range           Description
ColorTemperatureK      2000-10000      Color temperature in Kelvin
ColorAccuracy          0-100           Accuracy confidence (%)
RedComponent           0-255           R value from sensor
GreenComponent         0-255           G value from sensor
BlueComponent          0-255           B value from sensor
```

### Sensor Status DID (0xFD62)
```
Field                   Range           Description
SensorHealth           0-3             Sensor operational status
CalibrationStatus      0-2             Calibration state
SensorTemperature      -40 to 85       Sensor die temperature
CalibrationDrift       -100 to 100     Calibration drift (%)
```

## Test Scenarios by Feature

### Feature 1: Light Level Measurement
**Scenario: Measurement Accuracy Across Range**
```
Test Illumination Levels:
- Dark (0 lux) - Night time
- Low (10 lux) - Twilight
- Medium (500 lux) - Indoor office
- High (5,000 lux) - Outdoor cloudy
- Very High (50,000 lux) - Sunny day

Test Cases Needed:
1. Measurement accuracy at each level (±5% typical)
2. Sensor linearity across range
3. Response time to light changes
4. Saturation handling (> 65535 lux)
5. Low light noise floor (< 1 lux reading noise)
```

**Scenario: Rapid Light Changes**
```
Light Changes:
- Slow change (dawn/dusk): 1 lux/second
- Normal change (door opening): 10 lux/second
- Fast change (flash): 1000 lux/second
- Flicker detection (50/60Hz)

Test Cases Needed:
1. Handle slow light ramp
2. Detect normal transitions
3. Detect rapid changes
4. Filter flicker noise
5. Prevent false triggers
```

### Feature 2: Color Temperature Detection
**Scenario: Color Temperature Sensing**
```
Test Conditions:
- Incandescent light: 2,700K
- Fluorescent light: 4,000-5,000K
- Daylight: 5,500-6,500K
- Blue-enriched: 8,000K+

Test Cases Needed:
1. Color temperature measurement accuracy (±200K)
2. RGB component balance
3. Color compensation
4. Mixed light source handling
5. Temperature vs reference accuracy
```

### Feature 3: Day/Night Mode Detection
**Scenario: Automatic Day/Night Transition**
```
Thresholds:
- Night: < 10 lux
- Twilight: 10-100 lux
- Day: > 100 lux

Hysteresis:
- Day to Night: 80 lux
- Night to Day: 120 lux

Test Cases Needed:
1. Detect day mode (> 100 lux)
2. Detect night mode (< 10 lux)
3. Detect twilight (10-100 lux)
4. Hysteresis prevents flickering
5. Signal update timing
```

### Feature 4: Sensor Calibration
**Scenario: Calibration and Compensation**
```
Calibration Points:
- Dark calibration (0 lux)
- Reference illumination (1000 lux)
- Full scale calibration

Temperature Compensation:
- Measure sensor temperature
- Apply compensation factor
- Update calibration data

Test Cases Needed:
1. Factory calibration preserved
2. Field calibration update
3. Temperature compensation applied
4. Calibration drift detection
5. Automatic recalibration
```

### Feature 5: Data Filtering and Averaging
**Scenario: Noise Reduction**
```
Filtering Strategy:
- IIR filter (low pass)
- Moving average window
- Outlier rejection
- Rate-of-change limiting

Test Cases Needed:
1. Steady-state filtering
2. Noise reduction effectiveness
3. Response time after light change
4. Outlier detection and rejection
5. Filter parameter adjustment
```

### Feature 6: Threshold and Alert Detection
**Scenario: Threshold-Based Events**
```
Thresholds:
- Low light warning: 100 lux
- Very low light: 10 lux
- High light warning: 10,000 lux
- Sensor error: Invalid reading

Test Cases Needed:
1. Threshold crossing detection
2. Alert generation
3. Alert debouncing
4. Threshold hysteresis
5. Multiple threshold handling
```

## Mock Requirements

### ALS (Ambient Light Sensor) Mock
```cpp
class MockALS {
public:
    MOCK_METHOD(uint16_t, ReadLux, ());
    MOCK_METHOD(bool, IsReady, ());
    MOCK_METHOD(void, SetGain, (uint8_t gain));
    MOCK_METHOD(uint8_t, GetGain, ());
    MOCK_METHOD(bool, HasError, ());
};
```

### Color Sensor Mock
```cpp
class MockColorSensor {
public:
    MOCK_METHOD(void, ReadRGB, (uint8_t* r, uint8_t* g, uint8_t* b));
    MOCK_METHOD(uint16_t, GetColorTemperature, ());
    MOCK_METHOD(bool, IsCalibrated, ());
    MOCK_METHOD(void, CalibrateWhitePoint, ());
};
```

### Calibration Data Mock
```cpp
class MockCalibrationData {
public:
    MOCK_METHOD(void, LoadFactoryCalibration, ());
    MOCK_METHOD(uint16_t, GetCalibrationOffset, ());
    MOCK_METHOD(void, SaveCalibration, (uint16_t offset));
    MOCK_METHOD(float, GetTemperatureCompensation, (int8_t temp));
};
```

## Key Test Data

### Light Level Test Values (Lux)
```
BOUNDARY VALUES:
- Minimum: 0
- Very Low: 1, 5, 10
- Low: 50, 100
- Medium: 500, 1000
- High: 5000, 10000
- Very High: 50000, 100000
- Maximum: 65535

EQUIVALENCE PARTITIONS:
- Night: 0-10 lux
- Twilight: 10-100 lux
- Indoor: 100-1000 lux
- Outdoor: 1000-65535 lux
```

### Color Temperature Test Values (K)
```
BOUNDARY VALUES:
- Cold: 8000K, 9000K, 10000K
- Daylight: 5500K, 6500K, 7000K
- Warm: 3000K, 4000K, 5000K
- Very Warm: 2000K, 2700K

EQUIVALENCE PARTITIONS:
- Incandescent: 2700-3000K
- Fluorescent: 4000-5000K
- Daylight: 5500-6500K
- Cool: 7000-10000K
```

## Error Codes
```
0x00: No error
0x01: Sensor not ready
0x02: Sensor read error
0x03: I2C communication error
0x04: Out of range measurement
0x05: Calibration error
0x06: Temperature compensation error
0x07: Sensor overexposed
0x08: Sensor underexposed
0xFF: Unknown sensor error
```

## Common Test Patterns

### Pattern 1: Light Level Measurement Test
```robot
Test Case - Light Level Measurement At [Lux]
    Set Test Light    illumination=${lux}
    Wait For Sensor Stabilization    2s
    Read Light Level    ${measured}
    Verify Measurement Accuracy    ±5%
    Verify No Sensor Error
```

### Pattern 2: Color Temperature Test
```robot
Test Case - Color Temperature Detection [TemperatureK]
    Set Test Light    color_temp=${temperature}
    Wait For Color Stabilization    1s
    Read Color Temperature    ${measured}
    Verify Temperature Accuracy    ±200K
```

### Pattern 3: Day/Night Mode Test
```robot
Test Case - Day Mode Detection
    Set Test Light    illumination=500lux
    Wait For Mode Update
    Verify Day Mode Active
    Verify Illumination Signals Updated
```

## GTF Unit Test Structure

```cpp
TEST_F(AmbientSenseFixture, MeasurementAccuracyAtMediumLight)
{
    EXPECT_CALL(als_mock, ReadLux)
        .WillRepeatedly(Return(MEDIUM_LIGHT_VALUE));
    
    uint16_t reading = ambient_sense.GetAmbientLight();
    
    EXPECT_GE(reading, MEDIUM_LIGHT_MIN);
    EXPECT_LE(reading, MEDIUM_LIGHT_MAX);
}

TEST_F(AmbientSenseFixture, DayNightModeTransition)
{
    EXPECT_CALL(als_mock, ReadLux)
        .WillOnce(Return(500))   // Day
        .WillOnce(Return(50));   // Twilight
    
    ambient_sense.Update();
    EXPECT_EQ(ambient_sense.GetDayNightMode(), DAY_MODE);
    
    ambient_sense.Update();
    EXPECT_EQ(ambient_sense.GetDayNightMode(), TWILIGHT_MODE);
}

TEST_F(AmbientSenseFixture, ColorTemperatureDetection)
{
    EXPECT_CALL(color_mock, GetColorTemperature)
        .WillRepeatedly(Return(5500));  // Daylight
    
    uint16_t temp = ambient_sense.GetColorTemperature();
    
    EXPECT_GE(temp, 5300);
    EXPECT_LE(temp, 5700);
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P Ambient Sense Module
Resource       ../../resources/S3P_AmbientSense/s3p_ambientsense_pf.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
Light Level Measurement At Medium Illumination
    [Documentation]    Tests measurement accuracy at 500 lux
    [Tags]    integration    light-level    ambientsense
    Set Test Light    500lux
    Wait For Sensor Stabilization    2s
    Read Light Level
    Verify Measurement    within=500±25lux
    Verify Sensor Status    OK
    Verify No Errors

Color Temperature Detection Daylight
    [Documentation]    Tests color temp detection under daylight
    [Tags]    integration    color-temp
    Set Test Light    5500K
    Wait For Color Stabilization    1s
    Read Color Temperature
    Verify Temperature    within=5500±200K
    Verify RGB Balance

Day Mode Transition From Night
    [Documentation]    Validates transition to day mode
    [Tags]    integration    mode-transition
    Set Test Light    5lux
    Verify Night Mode Active
    Gradually Increase Light    to=500lux
    Wait For Mode Update    3s
    Verify Day Mode Active
    Verify Illumination Signals Updated
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85%
- **Branch Coverage**: ≥80%
- **Path Coverage**: ≥70%

### Functional Coverage
- ✓ Light level measurement across range
- ✓ Color temperature detection
- ✓ Day/night mode transitions
- ✓ Sensor calibration
- ✓ Data filtering and averaging
- ✓ Threshold detection
- ✓ Error handling and recovery
- ✓ Temperature compensation

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For sensor constants
- `test-strategy-planning` - For test planning

## Troubleshooting Common Issues

### Issue: Measurement Accuracy Low
- Check sensor calibration
- Verify light source stability
- Check filter settling time
- Validate sensor I2C communication

### Issue: Color Temperature Incorrect
- Verify RGB sensor calibration
- Check white point calibration
- Validate color matrix
- Check ambient lighting

### Issue: Day/Night Mode Flickering
- Increase hysteresis threshold
- Improve filtering algorithm
- Add debounce delay
- Check threshold values
