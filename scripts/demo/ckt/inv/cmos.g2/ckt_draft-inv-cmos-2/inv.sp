* CMOS inverter, the circuit cmos.g2 of the interface inv (demo library of Gazettoa)
* @RNL(type="header") { @VERSION("0.4"); @USE-PACKAGE(name="rnl-std-all", version="0.4");
*   @DEVICE(model="nch", terminals=["d", "g", "s", "b"], type="nmos");
*   @DEVICE(model="pch", terminals=["d", "g", "s", "b"], type="pmos");}
* The models nch and pch are not in the object: they come with the process (demo.lib, section tt).
.subckt inv a y vdd vss
M1 y a vdd vdd pch W=2.5u L=0.15u
M2 y a vss vss nch W=1u L=0.15u
* @RNL {
*   #M1 @PLACE(0, 6); #M2 @PLACE(0, 0);
*   #M1::s @ORIENT("up"); #M2::d @ORIENT("up");
*   {#M1 #M2} @ALIGN("x");
*   &vdd @ADD-TO $SUPPLY_NET_SET; &vss @ADD-TO $GROUND_NET_SET;
* }
* @RNL(type="generated", priority="high", author="rnl-solver 0.1", hash="sig2:1cdf194fe6dda43b.2c5e8a6652702034") {
*   %ground_stub_M2_s = $GROUND_STUB @ATTACH(gap=3) #M2::s;
*   %supply_stub_M1_s = $SUPPLY_STUB @ATTACH(gap=3) #M1::s;
*   %net_label_stub_M1_g = $NET_LABEL_STUB @ATTACH #M1::g;
*   %net_label_stub_M2_g = $NET_LABEL_STUB @ATTACH #M2::g;
*   %net_label_stub_M1_d = $NET_LABEL_STUB @ATTACH #M1::d;
*   %net_label_stub_M2_d = $NET_LABEL_STUB @ATTACH #M2::d;
*   %io_port_a = $IO_PORT @ATTACH &a;
*   %io_port_y = $IO_PORT @ATTACH &y;
*   %io_port_vdd = $IO_PORT @ATTACH &vdd;
*   %io_port_vss = $IO_PORT @ATTACH &vss;
*   #M1 @PLACE(0, 6) => @ORIENT("R0");
*   #M2 @PLACE(0, 0) => @ORIENT("R0");
*   %ground_stub_M2_s @PLACE(0, 0);
*   %ground_stub_M2_s::g @PLACE(0, -4) => @ORIENT("R0");
*   %supply_stub_M1_s @PLACE(0, 0);
*   %supply_stub_M1_s::s @PLACE(0, 10) => @ORIENT("R0");
*   %net_label_stub_M1_g @PLACE(0, 0);
*   %net_label_stub_M1_g::l @PLACE(-3, 6) => @ORIENT("R0");
*   %net_label_stub_M2_g @PLACE(0, 0);
*   %net_label_stub_M2_g::l @PLACE(-3, 0) => @ORIENT("R0");
*   %net_label_stub_M1_d @PLACE(0, 0);
*   %net_label_stub_M1_d::l @PLACE(0, 4) => @ORIENT("R90");
*   %net_label_stub_M2_d @PLACE(0, 0);
*   %net_label_stub_M2_d::l @PLACE(0, 2) => @ORIENT("R270");
*   %io_port_a @PLACE(-6, 12) => @ORIENT("R0");
*   %io_port_y @PLACE(-6, 8) => @ORIENT("R0");
*   %io_port_vdd @PLACE(-6, 4) => @ORIENT("R0");
*   %io_port_vss @PLACE(-6, 0) => @ORIENT("R0")
* }
.ends inv
* @RNL(type="generated", priority="high", author="rnl-solver 0.1", hash="sig2:c3d3eafd374ef4f4.53706929d5b144cf") {}
.end
