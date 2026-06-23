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
    // const history: Record<string, string>[] = [
    //     { role: 'system', content: 'You are a helpful assistant.' }
    // ];

    // while (true) {
    //     const input = await ask(rl, 'You: ');
    //     if (input.trim() === 'exit') { rl.close(); break; }

    //     history.push({ role: 'user', content: input });
    //     const reply = await llm(history) as string;
    //     history.push({ role: 'assistant', content: reply });
    //     console.log(`${C.assistant}Assistant: ${reply}${C.reset}\n`);
    // }

    console.log("calling an agent");
    const agentResponse = await startAgent('orchestrator');
    console.log({agentResponse});
}

main().catch((err) => {
    console.error(err);
    process.exit(1);
})
