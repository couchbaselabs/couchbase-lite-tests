# Jenkins Installation Steps :

1. Create .env file with DOCKERGID populated.

```
echo DOCKERGID=`getent group docker | cut -d: -f3` > .env
```

2. Run docker compose in the detach mode.

```
docker compose up -d
```

### Note: 

If running into the permission issue with /var/jenkins_home as below:

```
jenkins  | touch: cannot touch '/var/jenkins_home/copy_reference_file.log': Operation not permitted
jenkins  | Can not write to /var/jenkins_home/copy_reference_file.log. Wrong volume permissions?
```

Change UID / GID of /var/jenkins_home to 1000, which is the default UID / GID of the jenkins user.

```
 sudo chown -R 1000:1000 /var/jenkins_home
```