const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const productPage = fs.readFileSync(
  path.join(__dirname, '..', 'tomaspisar.cz', 'products', 'long-jump-replay', 'index.html'),
  'utf8'
);

test('product page describes qualified high-FPS camera support in English and Czech', () => {
  assert.match(productPage, /data-en="High-FPS camera support"/);
  assert.match(productPage, /including 120 FPS capture when supported by the camera, driver, and computer/);
  assert.match(productPage, /data-cs="Podpora kamer s vysokým FPS"/);
  assert.match(productPage, /včetně záznamu 120 FPS, pokud jej podporuje kamera, ovladač a počítač/);
});

test('product page publishes bilingual recommended event-system requirements', () => {
  assert.doesNotMatch(productPage, /Exact CPU and RAM requirements are not specified/);
  assert.doesNotMatch(productPage, /Přesné požadavky na procesor a RAM nejsou/);
  assert.match(productPage, /data-en="Windows 11, 64-bit" data-cs="Windows 11, 64bitový"/);
  assert.match(productPage, /Recent Intel Core i5 \/ AMD Ryzen 5 or better/);
  assert.match(productPage, /data-en="16 GB RAM" data-cs="16 GB RAM"/);
  assert.match(productPage, /SSD with at least 10 GB free and a Full HD \(1920 × 1080\) display/);
  assert.match(productPage, /USB 3 camera capable of 1280 × 720 at 60 FPS; 120 FPS is recommended/);
  assert.match(productPage, /test the complete computer, camera, cable, lighting, and recording mode before the event/);
});
