# Kind rename

Metadata and importing from several sources can be messy and in some cases Strava will export its acivity types/activity kinds under names like root='Ride' and not "Ride". That can lead to issues with tagging and the heatmap - in this case we have multiple, overlapping activity kinds for the same activity kinds.

To fix this, go to Admin -> Settings -> Kind rename

* Type in the box to define how you want to reprocess your activities
* The Format is `Existing name => New name`
* f.e. to rename `root='Ride'` to `'Ride'` put in `root='Ride' => Ride`
* Click on "Save", the system will then reprocess all affected activities
* This can take a few minutes depending on the amount of activities
