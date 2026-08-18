import { config } from "dotenv";
import { resolve } from "path";
import readline from 'node:readline';

import { startAgent } from './../../common';

config({ path: resolve(__dirname, "../../.env") });

const C = { user: "\x1b[96m", assistant: "\x1b[93m", reset: "\x1b[0m" };

function ask(rl: readline.Interface, prompt: string): Promise<string> {
    return new Promise(resolve => rl.question(`${C.user}${prompt}${C.reset}`, resolve));
}

async function main() {
    if (!process.env.AGENTS_KEY) {
        console.error("AGENTS_KEY not set");
        process.exit(1);
    }

    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });

    console.log("calling an agent");
    const agentResponse = await startAgent('navigate_with_user');
    console.log({agentResponse});
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
})
