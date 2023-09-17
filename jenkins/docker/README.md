# Jenkins Installation :

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

# Jenkins Docker Agent Setup:

1. From the docker host, ssh or attach to the jenkins machine and generate ED25519 key (Not RSA Key)

```
docker exec -it jenkins /bin/bash
ssh-keygen -t ed25519
```
By default, id_ed25519 and id_ed25519.pub file will be generated at /home/jenkins/.ssh.

2. From the docker host, create .env file with JENKINS_AGENT_SSH_PUBKEY populated with the public key from `id_ed25519.pub`.

```
echo JENKINS_AGENT_SSH_PUBKEY="<COPY THE PUBLIC KEY HERE>" >> .env
```

3. Run docker compose in the detach mode.

```
docker compose -f ./docker-compose-agent.yml up -d
```

4. Go the Jenkins Web Page, create a new credential with `SSH User Name with Private Key`.

* Username : jenkins
* Private key : < Copy from id_ed25519 >

5. Create a new node 

* Remote root directory : /home/jenkins
* Launch Method : Launch agent via ssh (Use Non Verifying Verification Strategy)
* Advance : Port 2200
