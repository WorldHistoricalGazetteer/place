// This script is used to merge any changes to the base configuration into the server's configuration file, avoiding the
// loss of mbtiles' metadata when the server is reconfigured. If the server is already running, it will require a restart
// to apply the changes.

// To prevent startup stalling, it also removes from the configuration file any references to mbtiles that are not
// present in the server's data directory.

const fs = require('fs');
const path = require('path');

const baseConfigPath = process.argv[2];
const configPath = process.argv[3];
const tilesDir = process.argv[4];

const fileExists = (filePath) => {
    try {
        return fs.existsSync(filePath);
    } catch (e) {
        return false;
    }
};

// Function to recursively scan a directory and process all its subdirectories
const scanDirectory = (dir, configData, isRoot = true) => {
    const mbtiles = require('mbtiles').mbtiles;
    if (fileExists(dir)) {
        const files = fs.readdirSync(dir);
        files.forEach((file) => {
            const filePath = path.join(dir, file);
            const stat = fs.statSync(filePath);

            if (stat.isDirectory()) {
                // If the file is a directory, recurse into it
                scanDirectory(filePath, configData, false);
            } else if (file.endsWith('.mbtiles') && !isRoot) {
                // If the file is a .mbtiles file, check if it exists in config
                const key = `${path.basename(dir)}-${path.basename(file, '.mbtiles')}`;
                if (!configData[key]) { // If the tileset is not already in config.json
                    console.log(`Adding tileset missing from config.json: ${file} from ${dir}`);
                    // Open the file and read the -A attribute from the `generator_options` field
                    const mbt = new mbtiles(filePath, (err) => {
                        if (err) {
                            console.error(`Error opening mbtiles file: ${filePath}`);
                            return;
                        }
                        mbt.getInfo((err, info) => {
                            if (err) {
                                console.error(`Error reading metadata from mbtiles file: ${filePath}`);
                                return;
                            }
                            configData[key] = {
                                // Remove the base directory from the path
                                mbtiles: filePath.replace(`${tilesDir}/`, ''),
                                tilejson: {
                                    attribution: info.attribution || "-unknown-"
                                }
                            };
                        });
                    });
                }
            }
        });
    }
};

try {

    if (!fileExists(baseConfigPath)) {
        console.error(`Base config file not found: ${baseConfigPath}`);
        process.exit(1);
    }

    if (!fileExists(configPath)) {
        console.error(`Config file not found: ${configPath}`);
        process.exit(1);
    }

    const baseConfig = JSON.parse(fs.readFileSync(baseConfigPath, 'utf8'));
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

    // Step 1: Loop through the data object and remove entries for missing mbtiles files
    for (const key in config.data) {
        if (config.data.hasOwnProperty(key) && (key.startsWith('datasets-') || key.startsWith('collections-'))) {
            const tile = config.data[key];
            if (tile.mbtiles && !fileExists(`${tilesDir}/${tile.mbtiles}`)) {
                console.log(`Removing config entry for missing tileset: ${tile.mbtiles} for key ${key}`);
                delete config.data[key]; // Remove the entry for this tile
            }
        }
    }

    // Step 2: Recursively add missing entries to the data object
    scanDirectory(tilesDir, config.data);

    // Step 3: Merge the processed config data into the base config
    baseConfig.data = config.data;

    // Step 4: Sort the keys of config.data numerically (natural sorting)
    const sortKeysNaturally = (data) => {
        const sortedKeys = Object.keys(data).sort((a, b) => {
            return a.localeCompare(b, undefined, { numeric: true });
        });

        const sortedData = {};
        sortedKeys.forEach((key) => {
            sortedData[key] = data[key];
        });

        return sortedData;
    };
    baseConfig.data = sortKeysNaturally(config.data);

    // Write the updated configuration back to the config file
    fs.writeFileSync(configPath, JSON.stringify(baseConfig, null, 2));
    console.log('Config updated and merged successfully');
} catch (error) {
    console.error('Error merging configs:', error);
    process.exit(1);
}
