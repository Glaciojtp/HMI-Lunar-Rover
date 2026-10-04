import struct
import unittest


class TestPaqueteControlBinario(unittest.TestCase):
    def test_tamano_paquete_control(self):
        # Estructura: int16 traccion_izq, int16 traccion_der, uint8 s1, uint8 s2, uint8 s3, uint8 s4
        # Little-endian: <hh4B
        formato = "<hh4B"
        tamano = struct.calcsize(formato)
        self.assertEqual(tamano, 8, f"El tamano esperado es 8 bytes, pero se calculo {tamano}")

    def test_empaquetado_y_desempaquetado_valores_limite(self):
        formato = "<hh4B"
        # Valores de prueba representativos
        trac_izq = -255
        trac_der = 255
        s1, s2, s3, s4 = 10, 90, 170, 90
        empaquetado = struct.pack(formato, trac_izq, trac_der, s1, s2, s3, s4)
        self.assertEqual(len(empaquetado), 8)

        desemp = struct.unpack(formato, empaquetado)
        self.assertEqual(desemp[0], -255)
        self.assertEqual(desemp[1], 255)
        self.assertEqual(desemp[2], 10)
        self.assertEqual(desemp[3], 90)
        self.assertEqual(desemp[4], 170)
        self.assertEqual(desemp[5], 90)


if __name__ == "__main__":
    unittest.main()
