/**
 * Critically damped spring on an angle with a speed limit (the standard "smooth damp" of game cameras).
 * error is the signed angle from the current heading to the target, in radians; velocity is the angular velocity the caller keeps.
 * Returns the step to rotate this frame and the new velocity. Unlike an eased turn with a speed cap, angular velocity is continuous:
 * a turn starts and ends smoothly, and a target that flips by up to 180 degrees never makes the view jump.
 */
export function smoothTurn(error: number, velocity: number, dt: number, smoothTime = 0.45, maxSpeed = THREE_MAX_SPEED): { step: number; velocity: number } {
  const omega = 2 / smoothTime, x = omega * dt, damp = 1 / (1 + x + 0.48 * x * x + 0.235 * x * x * x);
  const limit = maxSpeed * smoothTime;
  const change = Math.max(-limit, Math.min(limit, -error));
  const target = -change;
  const temp = (velocity + omega * change) * dt;
  let nextVelocity = (velocity - omega * temp) * damp;
  let step = target + (change + temp) * damp;
  if ((error > 0) === (step > error)) { step = error; nextVelocity = 0; }  // never overshoot the target
  return { step, velocity: nextVelocity };
}

const THREE_MAX_SPEED = (70 * Math.PI) / 180;  // radians per second: gentle enough to follow with the eye
