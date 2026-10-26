/// Gimbal/camera control commands are schema-generated - see
/// docs/schema/duml/commands.yaml and docs/schema/duml/README.md (awto-dji#33).
/// Regenerate with `python3 -I scripts/re/gen_duml_schema.py`; do not hand-edit any
/// generated/*.dart file.
library;

export 'generated/camera_request_i_frame.dart';
export 'generated/gimbal_abs_angle_control.dart';
export 'generated/gimbal_angle_control.dart';
export 'generated/gimbal_auto_calibration.dart';
export 'generated/gimbal_control.dart';
export 'generated/gimbal_speed_control.dart';
export 'generated/rc_request_gimbal_ctr_permission.dart';
