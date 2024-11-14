# Kind rename

Metadata and importing from several sources can be messy and in some cases Strava will export its acivity types/activity kinds under names like root='Ride' and not "Ride". That can lead to issues with tagging and the heatmap - in this case we have multiple, overlapping activity kinds for the same activity kinds.

![](https://private-user-images.githubusercontent.com/173824984/377596718-55176c07-f066-4354-bf02-01b637eda8ed.png?jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJnaXRodWIuY29tIiwiYXVkIjoicmF3LmdpdGh1YnVzZXJjb250ZW50LmNvbSIsImtleSI6ImtleTUiLCJleHAiOjE3MzE1NzQzNTgsIm5iZiI6MTczMTU3NDA1OCwicGF0aCI6Ii8xNzM4MjQ5ODQvMzc3NTk2NzE4LTU1MTc2YzA3LWYwNjYtNDM1NC1iZjAyLTAxYjYzN2VkYThlZC5wbmc_WC1BbXotQWxnb3JpdGhtPUFXUzQtSE1BQy1TSEEyNTYmWC1BbXotQ3JlZGVudGlhbD1BS0lBVkNPRFlMU0E1M1BRSzRaQSUyRjIwMjQxMTE0JTJGdXMtZWFzdC0xJTJGczMlMkZhd3M0X3JlcXVlc3QmWC1BbXotRGF0ZT0yMDI0MTExNFQwODQ3MzhaJlgtQW16LUV4cGlyZXM9MzAwJlgtQW16LVNpZ25hdHVyZT1kMTBmYmRkZjRhZWVhMmU0MjgyYWYwODM2ZjFlMTgzMTJiYzY1NDJkYTg4OWNlZWM1ZGU1NTRkYmRiYmI0NGVhJlgtQW16LVNpZ25lZEhlYWRlcnM9aG9zdCJ9.OgDaMh6Dh5h1163rns_jxi6lRlSo_kncGV7VqKTFNXM)

To fix this, go to Admin -> Settings -> Kind rename

* Type in the box to define how you want to reprocess your activities
* The Format is "Existing name => New name"
* f.e. to rename root='Ride' to 'Ride' put in root='Ride' => Ride 
* Click on "Save", the system will then reprocess all affected activities
* This can take a few minutes depending on the amount of activities
