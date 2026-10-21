/// A transparent, data-driven no-fly / altitude safety gate for the direct-control
/// app. Zones come from public airspace data; enforcement is standard geometry that
/// runs in the app and vets every control action before it becomes a DUML command.
///
/// This layer only ever *adds* restrictions. It does not and cannot remove any.
library geofence;

export 'src/geo.dart';
export 'src/zones.dart';
export 'src/geofence.dart';
