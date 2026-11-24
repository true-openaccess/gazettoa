* Two inverters in a row, the circuit two-inv.g1 of the interface buf2 (demo library of Gazettoa).
* The subcircuit inv is the circuit that uses.inv names; its symbol is the package of its interface.
* @RNL(type="header") { @VERSION("0.4"); @USE-PACKAGE(name="rnl-std-all", version="0.4"); @USE-PACKAGE(name="inv-sym", version="1.0");}
.subckt buf2 a y vdd vss
X1 a mid vdd vss inv
X2 mid y vdd vss inv
* @RNL {
*   {#X1 #X2} @SET-SYMBOL(terminals=["a", "y", "vdd", "vss"]) $INV;
*   #X1 @PLACE(0, 0); #X2 @PLACE(12, 0);
*   {#X1 #X2} @ORIENT("R0"); {#X1 #X2} @ALIGN("y");
*   &vdd @ADD-TO $SUPPLY_NET_SET; &vss @ADD-TO $GROUND_NET_SET;
* }
* @RNL(type="generated", priority="high", author="rnl-solver 0.1", hash="sig2:8a08f1756a5ccb57.881c4e68a6ae620e") {
*   %ground_stub_X1_vss = $GROUND_STUB @ATTACH(gap=3) #X1::vss;
*   %ground_stub_X2_vss = $GROUND_STUB @ATTACH(gap=3) #X2::vss;
*   %supply_stub_X1_vdd = $SUPPLY_STUB @ATTACH(gap=3) #X1::vdd;
*   %supply_stub_X2_vdd = $SUPPLY_STUB @ATTACH(gap=3) #X2::vdd;
*   %net_label_stub_X1_a = $NET_LABEL_STUB @ATTACH #X1::a;
*   %net_label_stub_X2_y = $NET_LABEL_STUB @ATTACH #X2::y;
*   %net_label_stub_X1_y = $NET_LABEL_STUB @ATTACH #X1::y;
*   %net_label_stub_X2_a = $NET_LABEL_STUB @ATTACH #X2::a;
*   %io_port_a = $IO_PORT @ATTACH &a;
*   %io_port_y = $IO_PORT @ATTACH &y;
*   %io_port_vdd = $IO_PORT @ATTACH &vdd;
*   %io_port_vss = $IO_PORT @ATTACH &vss;
*   #X1 @PLACE(0, 0) => @ORIENT("R0");
*   #X2 @PLACE(12, 0) => @ORIENT("R0");
*   %ground_stub_X1_vss @PLACE(0, 0);
*   %ground_stub_X1_vss::g @PLACE(0, -4) => @ORIENT("R0");
*   %ground_stub_X2_vss @PLACE(0, 0);
*   %ground_stub_X2_vss::g @PLACE(12, -4) => @ORIENT("R0");
*   %supply_stub_X1_vdd @PLACE(0, 0);
*   %supply_stub_X1_vdd::s @PLACE(0, 4) => @ORIENT("R0");
*   %supply_stub_X2_vdd @PLACE(0, 0);
*   %supply_stub_X2_vdd::s @PLACE(12, 4) => @ORIENT("R0");
*   %net_label_stub_X1_a @PLACE(0, 0);
*   %net_label_stub_X1_a::l @PLACE(-4, 0) => @ORIENT("R0");
*   %net_label_stub_X2_y @PLACE(0, 0);
*   %net_label_stub_X2_y::l @PLACE(16, 0) => @ORIENT("R180");
*   %net_label_stub_X1_y @PLACE(0, 0);
*   %net_label_stub_X1_y::l @PLACE(4, 0) => @ORIENT("R180");
*   %net_label_stub_X2_a @PLACE(0, 0);
*   %net_label_stub_X2_a::l @PLACE(8, 0) => @ORIENT("R0");
*   %io_port_a @PLACE(-6, 8) => @ORIENT("R0");
*   %io_port_y @PLACE(-6, 4) => @ORIENT("R0");
*   %io_port_vdd @PLACE(-6, 0) => @ORIENT("R0");
*   %io_port_vss @PLACE(-6, -4) => @ORIENT("R0")
* }
.ends buf2
* @RNL(type="generated", priority="high", author="rnl-solver 0.1", hash="sig2:96fbdfd69ed69f44.53706929d5b144cf") {}
.end
