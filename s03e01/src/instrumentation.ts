import { config } from 'dotenv';
import { resolve } from 'path';
config({ path: resolve(__dirname, '../../.env') });

import { NodeSDK } from '@opentelemetry/sdk-node';
import { LangfuseSpanProcessor } from '@langfuse/otel';

// Must be imported first, before any startObservation/startActiveObservation
// calls, so the span processor is registered before tracing starts.
export const sdk = new NodeSDK({
    spanProcessors: [new LangfuseSpanProcessor()],
});
sdk.start();
