import { Logger } from "./logger";

export const logger = new Logger({
    artifactDirectory: 'artifacts',
    level: 'info',
    sinks: ['console']
});
