```
This script is used to merge any changes to the base configuration into the server's configuration file, avoiding the 
loss of mbtiles' metadata when the server is reconfigured. If the server is already running, it will require a restart
to apply the changes.
```

const fs = require('fs');

const baseConfigPath = process.argv[2];
const configPath = process.argv[3];

try {
    const baseConfig = JSON.parse(fs.readFileSync(baseConfigPath, 'utf8'));
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    baseConfig.data = config.data;
    fs.writeFileSync(configPath, JSON.stringify(baseConfig, null, 2));
    console.log('Config merged successfully');
} catch (error) {
    console.error('Error merging configs:', error);
    process.exit(1);
}
