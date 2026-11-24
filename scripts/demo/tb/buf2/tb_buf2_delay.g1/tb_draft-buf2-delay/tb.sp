* Delay of each stage of a buffer driving four of its kind (demo library of Gazettoa)
* The block measured is the subcircuit buf2 (socket); X1.stage1 is its probe stage1, which the
* tool replaces with the net the evidence record gives (TOA 7.6).
Vdd vdd 0 {vdd}
Vin a 0 pulse(0 {vdd} 0.1n 20p 20p 1n 2n)
X1 a y vdd 0 buf2
X2 y o1 vdd 0 buf2
X3 y o2 vdd 0 buf2
X4 y o3 vdd 0 buf2
X5 y o4 vdd 0 buf2
.tran 1p 4.1n
.save v(a) v(y) v(X1.stage1)
