#!/bin/bash

java -Xmx8G -Xms8G -Duser.timezone=Europe/Helsinki -jar otp-shaded.jar --server --port 8080 --securePort 8081 --basePath ./ --graphs ./graphs --router hsl