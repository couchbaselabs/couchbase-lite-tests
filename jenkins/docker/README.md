# Jenkins Installation :

1. Create .env file with DOCKERGID populated.

```
echo DOCKERGID=`getent group docker | cut -d: -f3` > .env
```
The DOCKERGID is a group id of the `docker` user in the host machine.
The docker group id will be added to the `jenkins` container to allow
the jenkins to be able to use the docker on the host machine.  

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

3. Setup ssh key in the "agent" container

The `agent` container is a simple docker container that can be setup as a permanent node in Jenkins.
Before the container can be used in Jenkins, the `jenkins` user's ssh key needs to be generated and
setup to allow Jenkins to ssh to the `agent` container.    

3.1 Generate ed25519 ssh key (RSA key will not work) in the `jenkins` container.

```
docker exec -it jenkins /bin/bash
ssh-keygen -t ed25519
```
By default, `id_ed25519` (Private Key) and `id_ed25519.pub` (Public Key) file will be generated at /home/jenkins/.ssh directory.

3.2. Update `authorized_keys` file in the `agent` container with the public key from `id_ed25519.pub` generated in step 3.1.   

```
docker exec -it agent /bin/bash
cd /home/jenkins/.ssh
echo "<ssh-public-key-from-step-3.1>" > authorized_keys 
```
3.3 Test the ssh key setup by ssh to the `agent` container from the `jenkins` container.

```
docker exec -it agent /bin/bash
ssh jenkins@<agent ip address> -p 2200
```
3.4 Go the Jenkins Web Portal, create a new credential with `SSH User Name with Private Key`.

* Label : jenkins-ssh-key
* Username : jenkins
* Private key : < ssh-private-key-id_ed25519-from-step-3.1 >

3.5. Create a new permanent node on Jenkins Web Portal

* Remote root directory : /home/jenkins
* Launch Method : Launch agent via ssh with username `jenkins`, credential `jenkins-ssh-key`, and Non Verifying Verification Strategy
* Advance : Port 2200