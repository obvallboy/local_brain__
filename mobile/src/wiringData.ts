// Offline wiring reference — the pin maps for the hardware jobs, from the pibench
// profiles. Look these up on the phone while you're wiring at the bench. 3.3 V only.

export type WireRow = { chip: string; signal: string; pi: string };
export type Wiring = { id: string; title: string; note: string; rows: WireRow[] };

export const WIRINGS: Wiring[] = [
  {
    id: 'soic8-bios',
    title: 'SOIC-8 BIOS clip → Pi (SPI)',
    note: 'The Alienware BIOS job. Match pin 1 (the dot on the chip) to pin 1 on the clip. 3.3 V only — no level shifter.',
    rows: [
      { chip: '1', signal: 'CS#', pi: '24 — SPI0 CE0 (GPIO8)' },
      { chip: '2', signal: 'DO / MISO', pi: '21 — SPI0 MISO (GPIO9)' },
      { chip: '3', signal: 'WP#', pi: '1 or 17 — 3V3 (tie high)' },
      { chip: '4', signal: 'GND', pi: '6 — GND' },
      { chip: '5', signal: 'DI / MOSI', pi: '19 — SPI0 MOSI (GPIO10)' },
      { chip: '6', signal: 'CLK', pi: '23 — SPI0 SCLK (GPIO11)' },
      { chip: '7', signal: 'HOLD# / RESET#', pi: '1 or 17 — 3V3 (tie high)' },
      { chip: '8', signal: 'VCC', pi: '1 or 17 — 3V3' },
    ],
  },
  {
    id: 'i2c-eeprom',
    title: 'I²C EEPROM (24Cxx) → Pi',
    note: 'Where some laptops keep the password. A0/A1/A2 to GND = address 0x50. WP to GND = writable.',
    rows: [
      { chip: '1-3', signal: 'A0 A1 A2 (address)', pi: '6 — GND (for 0x50)' },
      { chip: '4', signal: 'GND', pi: '6 — GND' },
      { chip: '5', signal: 'SDA', pi: '3 — I2C1 SDA (GPIO2)' },
      { chip: '6', signal: 'SCL', pi: '5 — I2C1 SCL (GPIO3)' },
      { chip: '7', signal: 'WP', pi: '6 = writable / 1 = protected' },
      { chip: '8', signal: 'VCC', pi: '1 or 17 — 3V3' },
    ],
  },
  {
    id: 'uart',
    title: 'UART serial → Pi',
    note: '3.3 V ONLY — never a 5 V or RS-232 line. TX↔RX cross over. Do NOT connect the board’s Vcc.',
    rows: [
      { chip: 'GND', signal: 'common ground', pi: '6 — GND' },
      { chip: 'TX', signal: 'board TX → Pi RX', pi: '10 — UART RXD (GPIO15)' },
      { chip: 'RX', signal: 'board RX → Pi TX', pi: '8 — UART TXD (GPIO14)' },
    ],
  },
  {
    id: 'pi-header',
    title: 'Raspberry Pi 40-pin — key pins',
    note: 'The pins the jobs use. Count pin 1 at the corner nearest the SD card (with the USB ports toward you).',
    rows: [
      { chip: '3V3', signal: 'power', pi: 'pins 1, 17' },
      { chip: '5V', signal: 'power', pi: 'pins 2, 4' },
      { chip: 'GND', signal: 'ground', pi: '6, 9, 14, 20, 25, 30, 34, 39' },
      { chip: 'SPI0', signal: 'MOSI / MISO / SCLK', pi: '19 / 21 / 23' },
      { chip: 'SPI0', signal: 'CE0 / CE1', pi: '24 / 26' },
      { chip: 'I2C1', signal: 'SDA / SCL', pi: '3 / 5' },
      { chip: 'UART', signal: 'TXD / RXD', pi: '8 / 10' },
    ],
  },
];
