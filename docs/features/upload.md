# Uploading activities

Some users don't want to restart the application each time they add new activities but run it on their home server. For this use case you can upload activities. Uploading files is a potential security issue and it is protected with a password. This feature is only enabled when you have set a password in the configuration file.

Put the following into your configuration file:

```toml
[upload]
password = "fb1c8d62-07a5-47bf-ada1-30aa66e41d8a"
```

Be sure to choose your own password and not use the one from this documentation.

Then you can go to the upload page and see this form:

![upload-form.png](upload-form.png)

Select a file that you want to upload and a target directory within the “Activities” directory. Finally, enter the password from the configuration file.

After you have uploaded the file, you will be redirected to the parsed activity.