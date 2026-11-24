* Delay and power of an inverter driving four of its kind (demo library of Gazettoa)
* The block measured is the subcircuit inv (socket). The tool adds the circuit tested, the models
* and the parameter vdd of each run when it assembles the run (TOA 7.6).
Vdd vdd 0 {vdd}
Vin a 0 pulse(0 {vdd} 0.1n 20p 20p 1n 2n)
X1 a y vdd 0 inv
X2 y o1 vdd 0 inv
X3 y o2 vdd 0 inv
X4 y o3 vdd 0 inv
X5 y o4 vdd 0 inv
.tran 1p 4.1n
