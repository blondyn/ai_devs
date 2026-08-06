
import { Readable, Transform } from 'stream';
import { ReadableStream } from 'stream/web';
import unzipper from 'unzipper';


export type SensorComponent = 'humidity' | 'pressure' | 'temperature' | 'voltage' | 'water';
type SensorType =
    | SensorComponent
    | `${SensorComponent}/${SensorComponent}`
    | `${SensorComponent}/${SensorComponent}/${SensorComponent}`;

export interface SensorEntry {
    sensor_type: SensorType;
    timestamp: number;
    temperature_K: number;
    pressure_bar: number;
    water_level_meters: number;
    voltage_supply_v: number;
    humidity_percent: number;
    operator_notes: string;
}

const SENSORS_ZIP = 'https://hub.ag3nts.org/dane/sensors.zip';


export async function readSensorsZip(): Promise<Map<string, SensorEntry>> {
    const resp = await fetch(SENSORS_ZIP);
    if (!resp.ok) throw new Error(`Failed to fetch sensors.zip: ${resp.status}`);

    const entries = new Map<string, SensorEntry>();
    const nodeStream = Readable.fromWeb(resp.body as any);

    // readZip(new URL(SENSORS_ZIP));
    await new Promise<void>((resolve, reject) => {
                        const candidates = new Set();

        nodeStream
            .pipe(unzipper.Parse())
            .on('entry', (entry: unzipper.Entry) => {
                const WATCH_LIST = "9132-1522-2306-1048-2119".split('-')
                const thisIsTheFile = WATCH_LIST.some(str => entry.path.includes(str));

                const name = entry.path;
                if (!name.endsWith('.json')) { entry.autodrain(); return; }
                const chunks: Buffer[] = [];
                entry.on('data', (chunk: Buffer) => chunks.push(chunk));
                entry.on('end', () => {
                    try {
                        const data = Buffer.concat(chunks).toString();
                        const operatorNotes = JSON.parse(data).operator_notes;
                        const word_candidate = [operatorNotes[43], operatorNotes[59], operatorNotes[65], operatorNotes[73], operatorNotes[75]].join('');
                        if ((!word_candidate.includes(' ') && !word_candidate.match(/[\d,]+/))) {
                            candidates.add(word_candidate);
                        }
                        entries.set(name, JSON.parse(Buffer.concat(chunks).toString()));
                    } catch {
                        // skip malformed entries
                    }
                });
                entry.on('error', reject);
            })
            .on('finish', () => {
                for(let candidate of candidates) {
                    console.log(`time${candidate}`)
                }
                resolve();
            })
            .on('error', reject);
    });

    return entries;
}