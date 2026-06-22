export const VERIFY = "/verify";
export const PACKAGES = "/api/packages";
export const ACCESS_LEVEL = "/api/accesslevel";
export const LOCATION = "/api/location";

export const DATA_PEOPLE = (apiKey: string) => `/data/${apiKey}/people.csv`;
export const DATA_FINDHIM_LOCATIONS = (apiKey: string) => `/data/${apiKey}/findhim_locations.json`;
export const DATA_CATEGORIES = (apiKey: string) => `/data/${apiKey}/categorize.csv`;
export const DATA_ELECTRICITY = (apiKey: string) => `/data/${apiKey}/electricity.png`;
export const DATA_FAILURE = (apiKey: string) => `/data/${apiKey}/failure.log`;
export const DATA_ELECTRICITY_SOLUTION = "/i/solved_electricity.png";
export const DATA_DOC = "/dane/doc/";
export const DRONE_DOC = "/dane/drone.html";
export const DRONE_PNG = (apiKey:string) => `/data/${apiKey}/drone.png`;
