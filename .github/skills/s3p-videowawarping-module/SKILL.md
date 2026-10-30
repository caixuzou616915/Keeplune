---
name: s3p-videowawarping-module
description: >-
  Comprehensive reference for the S3P Video Warping & Output module (geometric warping,
  scaling, color space conversion, output rendering) for creating targeted unit and
  integration tests. Use when: writing test cases for video input processing, warp
  parameter validation, or output synchronization; working with DIDs 0xFD80-0xFD83.
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# S3P Video Warping & Output Module Skill

## Overview
This skill provides comprehensive information about the S3P Video Warping & Output module for creating targeted unit and integration tests. The Video Warping & Output module is responsible for processing, warping, and displaying video content with geometric corrections for the S3P SITS system.

## Module Purpose
The Video Warping & Output module manages:
- **Video input processing**: Receiving and validating video streams
- **Geometric warping**: Correcting display geometry distortion
- **Image scaling**: Resizing video to display resolution
- **Color space conversion**: Converting between video formats
- **Output rendering**: Sending corrected video to display
- **Frame rate management**: Synchronizing with display timing
- **Performance optimization**: Ensuring real-time processing

## Component Architecture

### External Interfaces
```
Video Warping & Output Module
├── Video Input Interface
│   ├── Camera feed (MIPI CSI, HDMI)
│   ├── Video format detection
│   ├── Frame buffer management
│   └── Input resolution support
│
├── Warping Engine
│   ├── Geometric correction matrices
│   ├── Distortion compensation
│   ├── Mesh-based warping
│   └── Performance optimization
│
├── Output Interface
│   ├── Display output (LVDS, MIPI DSI)
│   ├── Resolution scaling
│   ├── Frame rate control
│   └── Output synchronization
│
├── CAN Bus Interface (UDS)
│   ├── DID 0xFD80: Video Input Status
│   ├── DID 0xFD81: Warp Parameters
│   ├── DID 0xFD82: Output Status
│   └── DID 0xFD83: Performance Metrics
│
└── Signal Interface
    ├── Video enable signals
    ├── Warp mode signals
    └── Display sync signals
```

### Video Input Formats
```
Resolution Support:
- VGA: 640x480
- SVGA: 800x600
- XGA: 1024x768
- HD: 1280x720
- Full HD: 1920x1080
- 2K: 2560x1440
- 4K: 3840x2160

Frame Rates:
- 24 fps (cinematic)
- 30 fps (standard)
- 60 fps (smooth)
- 120 fps (high speed)

Color Formats:
- RGB888 (24-bit)
- RGB565 (16-bit)
- YCbCr 4:2:0
- ARGB8888 (with alpha)
```

## Key Data Structures

### Video Input Status DID (0xFD80)
```
Field                   Range           Description
InputResolutionWidth   0-4096          Input width in pixels
InputResolutionHeight  0-2160          Input height in pixels
InputFrameRate         24-240          Frames per second
ColorFormat            0-3             Current color space
IsLocked               0-1             Signal lock status
ErrorCount             0-65535         Input error count
```

### Warp Parameters DID (0xFD81)
```
Field                   Range           Description
WarpMode               0-3             0=None, 1=Barrel, 2=Pincushion, 3=Custom
WarpIntensity          0-100           Warp strength (%)
HorizontalShift        -100 to 100     H shift (% of width)
VerticalShift          -100 to 100     V shift (% of height)
AspectRatio            50-200          Aspect ratio (%)
```

### Output Status DID (0xFD82)
```
Field                   Range           Description
OutputResolutionWidth  0-4096          Output width in pixels
OutputResolutionHeight 0-2160          Output height in pixels
OutputFrameRate        24-240          Output frame rate
FrameDropCount         0-65535         Number of dropped frames
LatencyMs              0-100           Processing latency
```

### Performance Metrics DID (0xFD83)
```
Field                   Range           Description
ProcessingTimeMs       0-50            Time to process frame
CPUUsage               0-100           CPU usage percentage
MemoryUsage            0-100           Memory usage percentage
GPUUsage               0-100           GPU usage if available
ThermalStatus          0-3             Thermal state
```

## Test Scenarios by Feature

### Feature 1: Video Input Processing
**Scenario: Input Format Detection and Handling**
```
Input Formats to Test:
- 640x480 @ 30fps (VGA)
- 1280x720 @ 60fps (HD)
- 1920x1080 @ 30fps (Full HD)
- Various color formats

Test Cases Needed:
1. Detect input format automatically
2. Validate resolution support
3. Handle unsupported formats gracefully
4. Format change detection
5. Seamless format switching
```

**Scenario: Input Signal Lock and Loss**
```
Signal Conditions:
- Signal present and valid
- Signal degraded (noise)
- Signal lost (no input)
- Signal recovery

Test Cases Needed:
1. Detect signal lock
2. Report locked status
3. Detect signal loss
4. Recover from signal loss
5. Continuous monitoring
```

### Feature 2: Geometric Warping
**Scenario: Barrel Distortion Correction**
```
Barrel Distortion:
- Light: 5% correction
- Moderate: 15% correction
- Heavy: 30% correction

Test Cases Needed:
1. Apply barrel correction
2. Verify geometry accuracy
3. Edge pixel handling
4. Performance impact
5. Correction reversibility
```

**Scenario: Pincushion Distortion Correction**
```
Pincushion Distortion:
- Light: 5% correction
- Moderate: 15% correction
- Heavy: 30% correction

Test Cases Needed:
1. Apply pincushion correction
2. Verify geometry accuracy
3. Center preservation
4. Edge quality
5. Combined with other effects
```

**Scenario: Custom Mesh Warping**
```
Custom Meshes:
- Predefined meshes for different displays
- Mesh interpolation
- Real-time mesh updates
- Mesh validation

Test Cases Needed:
1. Load custom mesh
2. Apply mesh warping
3. Verify accuracy
4. Performance measurement
5. Mesh error detection
```

### Feature 3: Image Scaling and Aspect Ratio
**Scenario: Resolution Scaling**
```
Scaling Operations:
- Upscaling (lower to higher resolution)
- Downscaling (higher to lower resolution)
- No scaling (same resolution)
- Non-integer scaling

Test Cases Needed:
1. Upscale 640x480 to 1920x1080
2. Downscale 1920x1080 to 1280x720
3. Preserve aspect ratio
4. Quality assessment (aliasing, blur)
5. Scaling performance
```

**Scenario: Aspect Ratio Adjustment**
```
Aspect Ratios:
- 4:3 (traditional)
- 16:9 (standard)
- 21:9 (ultrawide)
- Custom ratios

Test Cases Needed:
1. Adjust aspect ratio
2. Verify output dimensions
3. Prevent distortion
4. Letterbox/pillarbox handling
5. Smooth transitions
```

### Feature 4: Color Space Conversion
**Scenario: RGB to YCbCr Conversion**
```
Color Spaces:
- RGB888 → YCbCr 4:2:0
- RGB888 → ARGB8888
- YCbCr 4:2:0 → RGB888

Test Cases Needed:
1. Accurate color conversion
2. No color shift
3. Chroma subsampling quality
4. Alpha channel handling
5. Conversion performance
```

### Feature 5: Frame Rate Control
**Scenario: Synchronization and Timing**
```
Frame Rate Scenarios:
- Lock to 30fps
- Lock to 60fps
- Match input frame rate
- Adaptive frame rate
- Frame dropping if needed

Test Cases Needed:
1. Frame rate lock accuracy
2. Timing synchronization
3. Dropped frame detection
4. Frame rate change handling
5. Latency measurement
```

**Scenario: Latency Management**
```
Latency Targets:
- Target: < 33ms (30fps)
- Target: < 16.7ms (60fps)
- Monitor: Measure actual latency
- Optimize: Improve if needed

Test Cases Needed:
1. Measure input to output latency
2. Identify bottlenecks
3. Verify target latency met
4. Monitor consistency
5. Thermal impact on latency
```

### Feature 6: Performance and Optimization
**Scenario: Real-Time Processing**
```
Performance Targets:
- CPU usage: < 80%
- Memory: < 500MB
- Latency: < 33ms
- Frame drops: 0 (ideal)

Test Cases Needed:
1. Monitor CPU usage
2. Monitor memory usage
3. Monitor latency
4. Count frame drops
5. Sustained performance over time
```

## Mock Requirements

### Video Input Handler Mock
```cpp
class MockVideoInput {
public:
    MOCK_METHOD(bool, ReceiveFrame, (VideoFrame* frame));
    MOCK_METHOD(bool, IsSignalLocked, ());
    MOCK_METHOD(uint32_t, GetInputResolution, ());
    MOCK_METHOD(uint8_t, GetFrameRate, ());
    MOCK_METHOD(uint8_t, GetColorFormat, ());
};
```

### Warping Engine Mock
```cpp
class MockWarpingEngine {
public:
    MOCK_METHOD(void, SetWarpMode, (uint8_t mode));
    MOCK_METHOD(void, SetWarpIntensity, (uint8_t intensity));
    MOCK_METHOD(bool, ProcessFrame, (VideoFrame* input, VideoFrame* output));
    MOCK_METHOD(void, SetCustomMesh, (const WarpMesh& mesh));
    MOCK_METHOD(uint32_t, GetProcessingTime, ());
};
```

### Display Output Mock
```cpp
class MockDisplayOutput {
public:
    MOCK_METHOD(void, SendFrame, (const VideoFrame& frame));
    MOCK_METHOD(void, SetOutputResolution, (uint32_t res));
    MOCK_METHOD(void, SetFrameRate, (uint8_t fps));
    MOCK_METHOD(bool, IsReady, ());
};
```

## Key Test Data

### Resolution Test Values
```
BOUNDARY VALUES (pixels):
- Minimum: 320x240
- VGA: 640x480
- HD: 1280x720
- Full HD: 1920x1080
- 4K: 3840x2160
- Maximum: 4096x2160

EQUIVALENCE PARTITIONS:
- Low: 320-640 width
- Medium: 800-1280 width
- High: 1920+ width
```

### Frame Rate Test Values
```
BOUNDARY VALUES (fps):
- Minimum: 24
- Standard: 30
- Smooth: 60
- High Speed: 120
- Maximum: 240

EQUIVALENCE PARTITIONS:
- Minimum: 24-30 fps
- Standard: 30-60 fps
- High: 60-120 fps
- Very High: 120+ fps
```

### Warp Intensity Test Values
```
BOUNDARY VALUES (%):
- None: 0
- Light: 10
- Moderate: 25
- Strong: 50
- Maximum: 100

EQUIVALENCE PARTITIONS:
- None: 0-5%
- Light: 5-20%
- Moderate: 20-50%
- Strong: 50-100%
```

## Error Codes
```
0x00: No error
0x01: Input signal lost
0x02: Invalid input format
0x03: Unsupported resolution
0x04: Unsupported frame rate
0x05: Warping calculation error
0x06: Memory allocation error
0x07: Output device not ready
0x08: Frame processing timeout
0x09: Performance degradation
0x0A: Thermal limit exceeded
0xFF: Unknown video error
```

## Common Test Patterns

### Pattern 1: Input Format Test
```robot
Test Case - Input Format [Resolution] At [FrameRate] FPS
    [Tags]    video-input    format
    Send Video Input    resolution=${resolution}    framerate=${framerate}
    Wait For Signal Lock    5s
    Verify Input Detected    ${resolution}    ${framerate}
    Verify No Input Errors
```

### Pattern 2: Warping Test
```robot
Test Case - Apply [WarpMode] Warping At [Intensity]%
    [Tags]    warping    distortion
    Enable Warp Mode    ${warp_mode}
    Set Warp Intensity    ${intensity}
    Process Test Frame
    Verify Warp Applied
    Verify Output Quality
```

### Pattern 3: Performance Test
```robot
Test Case - Performance Metrics At [Resolution] [FrameRate]FPS
    [Tags]    performance    real-time
    Set Video Input    ${resolution}    ${framerate}
    Measure Processing Metrics    duration=10s
    Verify CPU Usage    below=80%
    Verify Latency    below=33ms
    Verify Frame Drops    equal=0
```

## GTF Unit Test Structure

```cpp
TEST_F(VideoWarpingFixture, InputFormatDetection)
{
    EXPECT_CALL(input_mock, GetInputResolution)
        .WillOnce(Return(RES_1920x1080));
    EXPECT_CALL(input_mock, GetFrameRate)
        .WillOnce(Return(60));
    
    bool detected = video_warp.DetectInputFormat();
    
    EXPECT_TRUE(detected);
    EXPECT_EQ(video_warp.GetInputResolution(), RES_1920x1080);
}

TEST_F(VideoWarpingFixture, BarrelWarpApplication)
{
    EXPECT_CALL(warp_engine, SetWarpMode(WARP_BARREL)).Times(1);
    EXPECT_CALL(warp_engine, SetWarpIntensity(50)).Times(1);
    
    video_warp.SetWarpMode(WARP_BARREL);
    video_warp.SetWarpIntensity(50);
    
    EXPECT_EQ(video_warp.GetWarpMode(), WARP_BARREL);
    EXPECT_EQ(video_warp.GetWarpIntensity(), 50);
}

TEST_F(VideoWarpingFixture, FrameProcessingLatency)
{
    VideoFrame input_frame = CreateTestFrame(1920, 1080);
    VideoFrame output_frame;
    
    uint32_t start = GetMilliseconds();
    video_warp.ProcessFrame(&input_frame, &output_frame);
    uint32_t latency = GetMilliseconds() - start;
    
    EXPECT_LT(latency, 33);  // < 33ms for 30fps
}
```

## Robot Framework Integration Test Structure

```robot
*** Settings ***
Documentation  Integration Tests for S3P Video Warping Module
Resource       ../../resources/S3P_VideoInOutAndWarping/s3p_videowarp_pf.robot
Resource       ../../resources/S3P_Common/s3p_common_pf.robot

*** Test Cases ***
Input Format Detection 1920x1080 At 60FPS
    [Documentation]    Tests automatic input format detection
    [Tags]    integration    video-input    format-detection
    Send Video Input    resolution=1920x1080    framerate=60
    Wait For Signal Lock    3s
    Read Video Input Format
    Verify Resolution Detected    1920x1080
    Verify Frame Rate Detected    60fps
    Verify No Input Errors

Barrel Warp Correction Applied
    [Documentation]    Tests barrel distortion correction
    [Tags]    integration    warping    distortion
    Set Input    1280x720
    Enable Warp Mode    BARREL
    Set Warp Intensity    25%
    Process Test Pattern
    Verify Warp Applied
    Verify Geometry Corrected
    Verify Edge Quality

Real-Time Performance At Full HD 60FPS
    [Documentation]    Validates real-time processing capability
    [Tags]    integration    performance    real-time
    Set Video Input    1920x1080    60fps
    Run Performance Benchmark    duration=10s
    Verify CPU Usage    below=80%
    Verify Latency    below=16.7ms
    Verify Frame Drops    equal=0
    Verify Memory Stable
```

## Coverage Goals

### Code Coverage Targets
- **Line Coverage**: ≥85%
- **Branch Coverage**: ≥80%
- **Path Coverage**: ≥70%

### Functional Coverage
- ✓ Input format detection (all supported formats)
- ✓ Signal lock/loss handling
- ✓ Barrel distortion correction
- ✓ Pincushion distortion correction
- ✓ Custom mesh warping
- ✓ Resolution scaling (up and down)
- ✓ Aspect ratio adjustment
- ✓ Color space conversion
- ✓ Frame rate control and synchronization
- ✓ Performance monitoring
- ✓ Error handling and recovery

## Related Skills
- `robot-framework-integration` - For RF test implementation
- `test-design-techniques` - For test design patterns
- `test-documentation-compliance` - For test documentation
- `project-config-utilities` - For video-specific constants
- `test-strategy-planning` - For test planning

## Troubleshooting Common Issues

### Issue: Input Signal Not Locked
- Check video source connection
- Verify cable quality
- Check resolution support
- Validate timing parameters

### Issue: Warp Distortion Incorrect
- Verify warp mesh accuracy
- Check warp intensity setting
- Validate calculation precision
- Test on reference pattern

### Issue: Frame Drops Occurring
- Check CPU load
- Reduce resolution
- Lower frame rate
- Check thermal state

### Issue: Latency High
- Optimize warp algorithm
- Reduce resolution
- Check memory pressure
- Monitor CPU clock
