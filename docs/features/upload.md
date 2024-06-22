# Uploading activities

The original way of using this software was as a sort of “directory viewer” where you had all your data locally and could then start this program. It has a web-based user interface because that works easiest among different platforms. Qt is nice, but I've tried that for my last project ([Vigilant Crypto Snatch](https://martin-ueding.github.io/vigilant-crypto-snatch/)) and there people rather asked for a web interface because they wanted to run the program as a service elsewhere. Therefore, I've started this with a web UI directly.

Now users have asked for the option to upload activities. This becomes a potential security issue and it is protected with a password. This feature is only enabled when you have set a password in the configuration file.

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