# Docker Dev Env for Python Flask

# Running tests

This command builds a docker image with the code of this repository and runs the repository's tests

```sh
./build_docker.sh sleeper-backend
docker run -t sleeper-backend ./run_tests.sh
```

```
[+] Building 0.1s (10/10) FINISHED                                                            docker:default
 => [internal] load build definition from Dockerfile                                                    0.0s
 => => transferring dockerfile: 248B                                                                    0.0s
 => [internal] load metadata for docker.io/library/python:3.13.2-alpine3.21@sha256:323a717dc4a010fee21  0.0s
 => [internal] load .dockerignore                                                                       0.0s
 => => transferring context: 94B                                                                        0.0s
 => [1/5] FROM docker.io/library/python:3.13.2-alpine3.21@sha256:323a717dc4a010fee21e3f1aac738ee10bb48  0.0s
 => [internal] load build context                                                                       0.0s
 => => transferring context: 253B                                                                       0.0s
 => CACHED [2/5] WORKDIR /app                                                                           0.0s
 => CACHED [3/5] COPY requirements.txt .                                                                0.0s
 => CACHED [4/5] RUN pip install --no-cache-dir -r requirements.txt                                     0.0s
 => CACHED [5/5] COPY . .                                                                               0.0s
 => exporting to image                                                                                  0.0s
 => => exporting layers                                                                                 0.0s
 => => writing image sha256:4e6c980fbf83b2131359af3d3730e61c89ae7dc85e23c151114b0d9d4a749158            0.0s
 => => naming to docker.io/library/sleeper-backend                                                               0.0s

....
----------------------------------------------------------------------
Ran 4 tests in 0.069s

OK
```

# Running a specific test

This example runs a single test in the class TodoTestCase, with the name "test_home"

```sh
./build_docker.sh sleeper-backend
docker run -t sleeper-backend ./run_tests.sh TodoTestCase.test_home
```

# Running a flask dev server

Run this command to enable hot reloading via docker.

```sh
./build_docker.sh sleeper-backend
docker run -p 5000:5000 -v .:/app -t sleeper-backend flask init_db
docker run -p 5000:5000 -v .:/app -t sleeper-backend flask run --host=0.0.0.0 --port=5000
```
<!-- --network=host -->