// Public surface of the companion package. Nothing here is mounted by the app yet; see docs/parallel/phone-handoff.md.
export { PhoneCompanion, type PhoneCompanionProps } from "./PhoneCompanion";
export { LaptopPairing, phoneUrl, type LaptopPairingProps } from "./LaptopPairing";
export { useCompanionHost, type CompanionHost, type CompanionHostOptions } from "./useCompanionHost";
export { CompanionClient, REASON_TEXT, type ClientOptions, type ClientState } from "./client";
export { routeStateFromGuide, type RouteState, type StepAction, type LookMode, type Instruction } from "./protocol";
export { GyroLook, detectSensors, browserSensorEnv, lookFromOrientation, lookDelta, pulse, SENSOR_TEXT, type SensorStatus, type SensorEnv } from "./sensors";
