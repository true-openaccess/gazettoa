* Delay and power of an inverter driving four of its kind (demo library of Gazettoa)
.param vdd=1.8
* inv and the models (demo.lib) are added when the record is assembled (TOA 7.6)
Vdd vdd 0 {vdd}
Vin a 0 pulse(0 {vdd} 0.1n 20p 20p 1n 2n)
X1 a y vdd 0 inv
X2 y o1 vdd 0 inv
X3 y o2 vdd 0 inv
X4 y o3 vdd 0 inv
X5 y o4 vdd 0 inv
.tran 1p 4.1n
.meas tran tpd trig v(a) val='vdd/2' rise=1 targ v(y) val='vdd/2' fall=1
.meas tran pavg avg par('-i(Vdd)*vdd') from=0.1n to=4.1n
.end
