// This script is used to merge any changes to the base configuration into the server's configuration file, avoiding the
// loss of mbtiles' metadata when the server is reconfigured. If the server is already running, it will require a restart
// to apply the changes.

// To prevent startup stalling, it also removes from the configuration file any references to mbtiles that are not
// present in the server's data directory.

const fs = require('fs');

const baseConfigPath = process.argv[2];
const configPath = process.argv[3];

const fileExists = (path) => {
    try {
        return fs.existsSync(path);
    } catch (e) {
        return false;
    }
};

try {
    const baseConfig = JSON.parse(fs.readFileSync(baseConfigPath, 'utf8'));
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));

    // Remove data entries for missing mbtiles files
    if (config.data && Array.isArray(config.data)) {
        config.data = config.data.filter(tile => {
            if (tile.file && !fileExists(tile.file)) {
                console.log(`Removing missing tile file from configuration: ${tile.file}`);
                return false; // Exclude this tile entry
            }
            console.log(`Found configured tile file: ${tile.file}`);
            return true;
        });
    }

    // Merge the data from config into the base config
    baseConfig.data = config.data;

    // Write the updated configuration back to the config file
    fs.writeFileSync(configPath, JSON.stringify(baseConfig, null, 2));
    console.log('Config merged successfully');
} catch (error) {
    console.error('Error merging configs:', error);
    process.exit(1);
}
