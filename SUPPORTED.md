# Supported devices

The following devices have been tested and confirmed as working. If your device is unlisted but working, please open a pull request to update the list and add a fixture file (use `python -m devtools.dump_devinfo` to generate one).

> [!NOTE]
> The hub attached Tapo buttons S200B and S200D do not currently support alerting when the button is pressed.

> [!NOTE]
> Some firmware versions of Tapo Cameras will not authenticate unless you enable "Tapo Lab" > "Third-Party Compatibility" in the native Tapo app.
> Alternatively, you can factory reset and then prevent the device from accessing the internet.

<!--Do not edit text inside the SUPPORTED section below -->
<!--SUPPORTED_START-->
## Kasa devices

Some newer Kasa devices require authentication. These are marked with [^1] in the list below.<br>Hub-Connected Devices may work across TAPO/KASA branded hubs even if they don't work across the native apps.

### Plugs

- **EP10**
  - Hardware: 1.0 (US) / Firmware: 1.0.2
- **EP25**
  - Hardware: 2.6 (US) / Firmware: 1.0.1[^1]
  - Hardware: 2.6 (US) / Firmware: 1.0.2[^1]
- **HS100**
  - Hardware: 1.0 (UK) / Firmware: 1.2.6
  - Hardware: 4.1 (UK) / Firmware: 1.1.0[^1]
  - Hardware: 1.0 (US) / Firmware: 1.2.5
  - Hardware: 2.0 (US) / Firmware: 1.5.6
- **HS103**
  - Hardware: 1.0 (US) / Firmware: 1.5.7
  - Hardware: 2.1 (US) / Firmware: 1.1.2
  - Hardware: 2.1 (US) / Firmware: 1.1.4
- **HS105**
  - Hardware: 1.0 (US) / Firmware: 1.5.6
- **HS110**
  - Hardware: 1.0 (EU) / Firmware: 1.2.5
  - Hardware: 4.0 (EU) / Firmware: 1.0.4
  - Hardware: 1.0 (US) / Firmware: 1.2.6
- **KP100**
  - Hardware: 3.0 (US) / Firmware: 1.0.1
- **KP105**
  - Hardware: 1.0 (UK) / Firmware: 1.0.5
  - Hardware: 1.0 (UK) / Firmware: 1.0.7
- **KP115**
  - Hardware: 1.0 (EU) / Firmware: 1.0.16
  - Hardware: 1.0 (US) / Firmware: 1.0.17
  - Hardware: 1.0 (US) / Firmware: 1.0.21
- **KP125**
  - Hardware: 1.0 (US) / Firmware: 1.0.6
- **KP125M**
  - Hardware: 1.0 (US) / Firmware: 1.1.3[^1]
  - Hardware: 1.0 (US) / Firmware: 1.2.3[^1]
- **KP401**
  - Hardware: 1.0 (US) / Firmware: 1.0.0

### Power Strips

- **EP40**
  - Hardware: 1.0 (US) / Firmware: 1.0.2
- **EP40M**
  - Hardware: 1.0 (US) / Firmware: 1.1.0[^1]
- **HS107**
  - Hardware: 1.0 (US) / Firmware: 1.0.8
- **HS300**
  - Hardware: 1.0 (US) / Firmware: 1.0.10
  - Hardware: 1.0 (US) / Firmware: 1.0.21
  - Hardware: 2.0 (US) / Firmware: 1.0.12
  - Hardware: 2.0 (US) / Firmware: 1.0.3
- **KP200**
  - Hardware: 3.0 (US) / Firmware: 1.0.3
- **KP303**
  - Hardware: 1.0 (UK) / Firmware: 1.0.3
  - Hardware: 2.0 (US) / Firmware: 1.0.3
  - Hardware: 2.0 (US) / Firmware: 1.0.9
- **KP400**
  - Hardware: 1.0 (US) / Firmware: 1.0.10
  - Hardware: 2.0 (US) / Firmware: 1.0.6
  - Hardware: 3.0 (US) / Firmware: 1.0.3
  - Hardware: 3.0 (US) / Firmware: 1.0.4

### Wall Switches

- **ES20M**
  - Hardware: 1.0 (US) / Firmware: 1.0.11
  - Hardware: 1.0 (US) / Firmware: 1.0.8
- **HS200**
  - Hardware: 2.0 (US) / Firmware: 1.5.7
  - Hardware: 3.0 (US) / Firmware: 1.1.5
  - Hardware: 5.0 (US) / Firmware: 1.0.11
  - Hardware: 5.0 (US) / Firmware: 1.0.2
  - Hardware: 5.26 (US) / Firmware: 1.0.3[^1]
- **HS210**
  - Hardware: 1.0 (US) / Firmware: 1.5.8
  - Hardware: 2.0 (US) / Firmware: 1.1.5
  - Hardware: 3.0 (US) / Firmware: 1.0.10
- **HS220**
  - Hardware: 1.0 (US) / Firmware: 1.5.7
  - Hardware: 2.0 (US) / Firmware: 1.0.3
  - Hardware: 3.26 (US) / Firmware: 1.0.1[^1]
- **KP405**
  - Hardware: 1.0 (US) / Firmware: 1.0.5
  - Hardware: 1.0 (US) / Firmware: 1.0.6
- **KS200**
  - Hardware: 1.0 (US) / Firmware: 1.0.8
- **KS200M**
  - Hardware: 1.0 (US) / Firmware: 1.0.10
  - Hardware: 1.0 (US) / Firmware: 1.0.11
  - Hardware: 1.0 (US) / Firmware: 1.0.12
  - Hardware: 1.0 (US) / Firmware: 1.0.8
- **KS205**
  - Hardware: 1.0 (US) / Firmware: 1.0.2[^1]
  - Hardware: 1.0 (US) / Firmware: 1.1.0[^1]
- **KS220**
  - Hardware: 1.0 (US) / Firmware: 1.0.13
- **KS220M**
  - Hardware: 1.0 (US) / Firmware: 1.0.4
- **KS225**
  - Hardware: 1.0 (US) / Firmware: 1.0.2[^1]
  - Hardware: 1.0 (US) / Firmware: 1.1.0[^1]
  - Hardware: 1.0 (US) / Firmware: 1.1.1[^1]
- **KS230**
  - Hardware: 1.0 (US) / Firmware: 1.0.14
  - Hardware: 2.0 (US) / Firmware: 1.0.11
- **KS240**
  - Hardware: 1.0 (US) / Firmware: 1.0.4[^1]
  - Hardware: 1.0 (US) / Firmware: 1.0.5[^1]
  - Hardware: 1.0 (US) / Firmware: 1.0.7[^1]
  - Hardware: 1.0 (US) / Firmware: 1.0.9[^1]

### Bulbs

- **KL110**
  - Hardware: 1.0 (US) / Firmware: 1.8.11
- **KL120**
  - Hardware: 1.0 (US) / Firmware: 1.8.11
  - Hardware: 1.0 (US) / Firmware: 1.8.6
- **KL125**
  - Hardware: 1.20 (US) / Firmware: 1.0.5
  - Hardware: 2.0 (US) / Firmware: 1.0.7
  - Hardware: 4.0 (US) / Firmware: 1.0.5
- **KL130**
  - Hardware: 1.0 (EU) / Firmware: 1.8.8
  - Hardware: 1.0 (US) / Firmware: 1.8.11
- **KL135**
  - Hardware: 1.0 (US) / Firmware: 1.0.15
  - Hardware: 1.0 (US) / Firmware: 1.0.6
- **KL50**
  - Hardware: 1.0 (US) / Firmware: 1.1.13
- **KL60**
  - Hardware: 1.0 (UN) / Firmware: 1.1.4
  - Hardware: 1.0 (US) / Firmware: 1.1.13
- **LB110**
  - Hardware: 1.0 (US) / Firmware: 1.8.11

### Light Strips

- **KL400L5**
  - Hardware: 1.0 (US) / Firmware: 1.0.5
  - Hardware: 1.0 (US) / Firmware: 1.0.8
- **KL420L5**
  - Hardware: 1.0 (US) / Firmware: 1.0.2
- **KL430**
  - Hardware: 2.0 (UN) / Firmware: 1.0.8
  - Hardware: 1.0 (US) / Firmware: 1.0.10
  - Hardware: 2.0 (US) / Firmware: 1.0.11
  - Hardware: 2.0 (US) / Firmware: 1.0.8
  - Hardware: 2.0 (US) / Firmware: 1.0.9

### Hubs

- **KH100**
  - Hardware: 1.0 (EU) / Firmware: 1.2.3[^1]
  - Hardware: 1.0 (EU) / Firmware: 1.5.12[^1]
  - Hardware: 1.0 (UK) / Firmware: 1.5.6[^1]

### Hub-Connected Devices

- **KE100**
  - Hardware: 1.0 (EU) / Firmware: 2.4.0[^1]
  - Hardware: 1.0 (EU) / Firmware: 2.8.0[^1]
  - Hardware: 1.0 (UK) / Firmware: 2.8.0[^1]


## Tapo devices

All Tapo devices require authentication.<br>Hub-Connected Devices may work across TAPO/KASA branded hubs even if they don't work across the native apps.

### Plugs

- **P100**
  - Hardware: 1.0.0 (US) / Firmware: 1.1.3
  - Hardware: 1.0.0 (US) / Firmware: 1.3.7
  - Hardware: 1.0.0 (US) / Firmware: 1.4.0
- **P110**
  - Hardware: 1.0 (AU) / Firmware: 1.3.1
  - Hardware: 1.0 (EU) / Firmware: 1.0.7
  - Hardware: 1.0 (EU) / Firmware: 1.2.3
  - Hardware: 1.0 (UK) / Firmware: 1.3.0
- **P110M**
  - Hardware: 1.0 (AU) / Firmware: 1.2.3
  - Hardware: 1.0 (EU) / Firmware: 1.2.3
- **P115**
  - Hardware: 1.0 (EU) / Firmware: 1.2.3
  - Hardware: 1.0 (US) / Firmware: 1.1.3
- **P125M**
  - Hardware: 1.0 (US) / Firmware: 1.1.0
- **P135**
  - Hardware: 1.0 (US) / Firmware: 1.0.5
  - Hardware: 1.0 (US) / Firmware: 1.2.0
- **TP15**
  - Hardware: 1.0 (US) / Firmware: 1.0.3

### Power Strips

- **P210M**
  - Hardware: 1.0 (US) / Firmware: 1.0.3
- **P300**
  - Hardware: 1.0 (EU) / Firmware: 1.0.13
  - Hardware: 1.0 (EU) / Firmware: 1.0.15
  - Hardware: 1.0 (EU) / Firmware: 1.0.7
- **P304M**
  - Hardware: 1.0 (UK) / Firmware: 1.0.3
- **P306**
  - Hardware: 1.0 (US) / Firmware: 1.1.2
- **TP25**
  - Hardware: 1.0 (US) / Firmware: 1.0.2

### Wall Switches

- **S210**
  - Hardware: 1.0 (EU) / Firmware: 1.9.0
- **S220**
  - Hardware: 1.0 (EU) / Firmware: 1.9.0
- **S500D**
  - Hardware: 1.0 (US) / Firmware: 1.0.5
- **S505**
  - Hardware: 1.0 (US) / Firmware: 1.0.2
- **S505D**
  - Hardware: 1.0 (US) / Firmware: 1.1.0

### Bulbs

- **L510B**
  - Hardware: 3.0 (EU) / Firmware: 1.0.5
- **L510E**
  - Hardware: 3.0 (US) / Firmware: 1.0.5
  - Hardware: 3.0 (US) / Firmware: 1.1.2
- **L530B**
  - Hardware: 3.0 (EU) / Firmware: 1.1.9
- **L530E**
  - Hardware: 3.0 (EU) / Firmware: 1.0.6
  - Hardware: 3.0 (EU) / Firmware: 1.1.0
  - Hardware: 3.0 (EU) / Firmware: 1.1.6
  - Hardware: 2.0 (TW) / Firmware: 1.1.1
  - Hardware: 2.0 (US) / Firmware: 1.1.0
- **L630**
  - Hardware: 1.0 (EU) / Firmware: 1.1.2

### Light Strips

- **L900-10**
  - Hardware: 1.0 (EU) / Firmware: 1.0.17
  - Hardware: 1.0 (US) / Firmware: 1.0.11
- **L900-5**
  - Hardware: 1.0 (EU) / Firmware: 1.0.17
  - Hardware: 1.0 (EU) / Firmware: 1.1.0
- **L920-5**
  - Hardware: 1.0 (EU) / Firmware: 1.0.7
  - Hardware: 1.0 (EU) / Firmware: 1.1.3
  - Hardware: 1.0 (US) / Firmware: 1.1.0
  - Hardware: 1.0 (US) / Firmware: 1.1.3
- **L930-5**
  - Hardware: 1.0 (EU) / Firmware: 1.2.5
  - Hardware: 1.0 (US) / Firmware: 1.1.2

### Cameras

- **C100**
  - Hardware: 4.0 / Firmware: 1.3.14
- **C110**
  - Hardware: 2.0 (EU) / Firmware: 1.4.3
- **C210**
  - Hardware: 2.0 / Firmware: 1.3.11
  - Hardware: 2.0 (EU) / Firmware: 1.4.2
  - Hardware: 2.0 (EU) / Firmware: 1.4.3
- **C220**
  - Hardware: 1.0 (EU) / Firmware: 1.2.2
- **C225**
  - Hardware: 2.0 (US) / Firmware: 1.0.11
- **C325WB**
  - Hardware: 1.0 (EU) / Firmware: 1.1.17
- **C520WS**
  - Hardware: 1.0 (US) / Firmware: 1.2.8
- **C720**
  - Hardware: 1.0 (US) / Firmware: 1.2.3
- **TC65**
  - Hardware: 1.0 / Firmware: 1.3.9
- **TC70**
  - Hardware: 3.0 / Firmware: 1.3.11

### Doorbells and chimes

- **D100C**
  - Hardware: 1.0 (US) / Firmware: 1.1.3
- **D130**
  - Hardware: 1.0 (US) / Firmware: 1.1.9
- **D230**
  - Hardware: 1.20 (EU) / Firmware: 1.1.19

### Vacuums

- **RV20 Max Plus**
  - Hardware: 1.0 (EU) / Firmware: 1.0.7
- **RV30 Max**
  - Hardware: 1.0 (US) / Firmware: 1.2.0

### Hubs

- **H100**
  - Hardware: 1.0 (AU) / Firmware: 1.5.23
  - Hardware: 1.0 (EU) / Firmware: 1.2.3
  - Hardware: 1.0 (EU) / Firmware: 1.5.10
  - Hardware: 1.0 (EU) / Firmware: 1.5.5
- **H200**
  - Hardware: 1.0 (EU) / Firmware: 1.3.2
  - Hardware: 1.0 (EU) / Firmware: 1.3.6
  - Hardware: 1.0 (US) / Firmware: 1.3.6

### Hub-Connected Devices

- **S200B**
  - Hardware: 1.0 (EU) / Firmware: 1.11.0
  - Hardware: 1.0 (US) / Firmware: 1.12.0
- **S200D**
  - Hardware: 1.0 (EU) / Firmware: 1.11.0
  - Hardware: 1.0 (EU) / Firmware: 1.12.0
- **T100**
  - Hardware: 1.0 (EU) / Firmware: 1.12.0
  - Hardware: 1.0 (US) / Firmware: 1.12.0
- **T110**
  - Hardware: 1.0 (EU) / Firmware: 1.8.0
  - Hardware: 1.0 (EU) / Firmware: 1.9.0
  - Hardware: 1.0 (US) / Firmware: 1.9.0
- **T300**
  - Hardware: 1.0 (EU) / Firmware: 1.7.0
- **T310**
  - Hardware: 1.0 (EU) / Firmware: 1.5.0
  - Hardware: 1.0 (US) / Firmware: 1.5.0
- **T315**
  - Hardware: 1.0 (EU) / Firmware: 1.7.0
  - Hardware: 1.0 (US) / Firmware: 1.8.0


<!--SUPPORTED_END-->
[^1]: Model requires authentication
