#!/bin/bash

set -e

GRAPH_DIR="graphs"
ROUTER_NAME="hsl"

rm -rf $GRAPH_DIR/$ROUTER_NAME/ || true
mkdir -p $GRAPH_DIR/$ROUTER_NAME/

HSL_ROUTER_ZIP_NAME="router-hsl.zip"
wget "https://api.digitransit.fi/routing-data/v2/hsl/router-hsl.zip" -O $HSL_ROUTER_ZIP_NAME

unzip -o $HSL_ROUTER_ZIP_NAME
HSL_ROUTER_FOLDER_NAME=$(unzip -Z -1 $HSL_ROUTER_ZIP_NAME | head -1)
cp ./$HSL_ROUTER_FOLDER_NAME/*.json ./$GRAPH_DIR/$ROUTER_NAME/
cp ./$HSL_ROUTER_FOLDER_NAME/HSLlautta.zip ./$GRAPH_DIR/$ROUTER_NAME/hsl-lautta.gtfs.zip
rm -r $HSL_ROUTER_FOLDER_NAME/ $HSL_ROUTER_ZIP_NAME

sed -i 's/"osmWayPropertySet": "finland",/"osmWayPropertySet": "default",/' ./$GRAPH_DIR/$ROUTER_NAME/build-config.json
sed -i 's/"fares": "HSL",/"fares": "default",/' ./$GRAPH_DIR/$ROUTER_NAME/build-config.json
sed -i 's/"routePreferenceSettings": "HSL",/"routePreferenceSettings": "HSL"/' ./$GRAPH_DIR/$ROUTER_NAME/router-config.json
sed -i '/\"updaters\"/,/]/ d; /^$/d' ./$GRAPH_DIR/$ROUTER_NAME/router-config.json

wget "https://infopalvelut.storage.hsldev.com/gtfs/hsl.zip" -O ./$GRAPH_DIR/$ROUTER_NAME/hsl.gtfs.zip
wget "https://karttapalvelu.storage.hsldev.com/hsl.osm/hsl.osm.pbf" -O ./$GRAPH_DIR/$ROUTER_NAME/hsl.osm.pbf

VERSION=1.5.0
wget "https://repo1.maven.org/maven2/org/opentripplanner/otp/$VERSION/otp-$VERSION-shaded.jar" -O otp-shaded.jar
java -Xmx8G -Xms8G -jar otp-shaded.jar --build $GRAPH_DIR/$ROUTER_NAME

printf "#!/bin/bash\n\njava -Xmx8G -Xms8G -Duser.timezone=Europe/Helsinki -jar otp-shaded.jar --server --port 8080 --securePort 8081 --basePath ./ --graphs ./$GRAPH_DIR --router $ROUTER_NAME" > run_again.sh

java -Xmx8G -Xms8G -Duser.timezone=Europe/Helsinki -jar otp-shaded.jar --server --port 8080 --securePort 8081 --basePath ./ --graphs ./$GRAPH_DIR --router $ROUTER_NAME