using CircularProgressBar;
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.IO.Ports;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace WindowsFormsApp4
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
        }

        private void Form1_Load(object sender, EventArgs e)
        {
            this.KeyPreview = true;

            pbW.Image = Properties.Resources.w_off;
            pbA.Image = Properties.Resources.a_off;
            pbS.Image = Properties.Resources.s_off;
            pbD.Image = Properties.Resources.d_off;
            pbStop.Image = Properties.Resources.stop_off;

          
        }

        private void Form1_FormClosing(object sender, FormClosingEventArgs e)
        {
            if (ppp.IsOpen)
            {
                ppp.Close();
            }
        }

        private void button1_Click(object sender, EventArgs e)
        {
            try
            {
                ppp.Open();
            }
            catch(Exception ex)
            {
                MessageBox.Show(ex.Message);
            }

        }

        private void button1_MouseEnter(object sender, EventArgs e)
        {
            button1.BackColor = Color.Lime;
        }

        private void button1_MouseLeave(object sender, EventArgs e)
        {
            button1.BackColor = Color.DodgerBlue;
        }

        private void serialPort1_DataReceived(object sender, SerialDataReceivedEventArgs e)
        {
            while (ppp.IsOpen && ppp.BytesToRead > 0)
            {
                try
                {
                    string data = ppp.ReadLine().Trim();

                    // FORMATO:
                    // temp,hum,lux
                    // ejemplo:
                    // 13,62,1

                    string[] v = data.Split(',');

                    if (v.Length >= 3)
                    {
                        if (int.TryParse(v[0], out int temp) &&
                            int.TryParse(v[1], out int hum) &&
                            int.TryParse(v[2], out int lux))
                        {
                            this.Invoke((MethodInvoker)(() =>
                            {
                                // =====================================
                                // TEMPERATURA
                                // =====================================

                                circularProgressBar1.Value =
                                    Math.Min(temp, circularProgressBar1.Maximum);

                                circularProgressBar1.Text =
                                    temp.ToString();

                                // =====================================
                                // HUMEDAD
                                // =====================================

                                circularProgressBar2.Value =
                                    Math.Min(hum, circularProgressBar2.Maximum);

                                circularProgressBar2.Text =
                                    hum.ToString();

                                // =====================================
                                // LUX
                                // =====================================

                                circularProgressBar3.Value =
                                    Math.Min(lux, circularProgressBar3.Maximum);

                                circularProgressBar3.Text =
                                    lux.ToString();

                                // =====================================
                                // GRÁFICOS
                                // =====================================

                                chart1.Series["TEMPERATURA"]
                                    .Points.AddY(temp);

                                chart1.Series["HUMEDAD"]
                                    .Points.AddY(hum);

                                chart1.Series["LUX"]
                                    .Points.AddY(lux);

                                // =====================================
                                // LIMITAR PUNTOS
                                // =====================================

                                if (chart1.Series["TEMPERATURA"]
                                    .Points.Count > 50)
                                {
                                    chart1.Series["TEMPERATURA"]
                                        .Points.RemoveAt(0);
                                }

                                if (chart1.Series["HUMEDAD"]
                                    .Points.Count > 50)
                                {
                                    chart1.Series["HUMEDAD"]
                                        .Points.RemoveAt(0);
                                }

                                if (chart1.Series["LUX"]
                                    .Points.Count > 50)
                                {
                                    chart1.Series["LUX"]
                                        .Points.RemoveAt(0);
                                }
                            }));
                        }
                    }
                }
                catch (Exception ex)
                {
                    MessageBox.Show(
                        "Error al recibir datos:\n" + ex.Message);
                }
            }
        }
        void EnviarComando(string cmd)
        {
            try
            {
                if (!ppp.IsOpen)
                {
                    MessageBox.Show("Puerto no abierto");
                    return;
                }

                ppp.WriteLine(cmd);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error: " + ex.Message);
            }
        }

        private void Form1_KeyDown(object sender, KeyEventArgs e)
        {
            try
            {
                if (e.KeyCode == Keys.W)
                {
                    pbW.Image = Properties.Resources.w_on;
                    EnviarComando("avz");
                }

                if (e.KeyCode == Keys.S)
                {
                    pbS.Image = Properties.Resources.s_on;
                    EnviarComando("rct");
                }

                if (e.KeyCode == Keys.A)
                {
                    pbA.Image = Properties.Resources.a_on;
                    EnviarComando("izq");
                }

                if (e.KeyCode == Keys.D)
                {
                    pbD.Image = Properties.Resources.d_on;
                    EnviarComando("der");
                }

                if (e.KeyCode == Keys.P)
                {
                    pbStop.Image = Properties.Resources.stop_on;
                    EnviarComando("stp");
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show("Error teclado: " + ex.Message);
            }
        }

        private void Form1_KeyUp(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.W)
                pbW.Image = Properties.Resources.w_off;

            if (e.KeyCode == Keys.S)
                pbS.Image = Properties.Resources.s_off;

            if (e.KeyCode == Keys.A)
                pbA.Image = Properties.Resources.a_off;

            if (e.KeyCode == Keys.D)
                pbD.Image = Properties.Resources.d_off;

            if (e.KeyCode == Keys.P)
                pbStop.Image = Properties.Resources.stop_off;
        }


        private void circularProgressBar2_Click(object sender, EventArgs e)
        {

        }

        private void pictureBox1_Click(object sender, EventArgs e)
        {

        }

        private void circularProgressBar3_Click(object sender, EventArgs e)
        {

        }

        private void chart1_Click(object sender, EventArgs e)
        {

        }

        private void pictureBox6_Click(object sender, EventArgs e)
        {

        }
    }
}
